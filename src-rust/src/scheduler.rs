use crate::capital_model::predict_capital;
use crate::config::{ConfigMap, get_bool};
use crate::exporter;
use crate::market_pid::{attach_market_relative_metrics, estimate_market_pid};
use crate::pattern_model::predict_pattern;
use crate::schemas::{DailySample, MarketPidSnapshot, PatternResult, PredictResult};
use anyhow::Result;
use csv::ReaderBuilder;
use encoding_rs::GB18030;
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Instant;

fn iter_stock_dirs(d: &Path) -> Vec<PathBuf> {
    let mut v: Vec<PathBuf> = fs::read_dir(d).ok()
        .map(|e| e.filter_map(|e| e.ok()).filter(|e| e.path().is_dir()).map(|e| e.path()).collect())
        .unwrap_or_default();
    v.sort(); v
}
fn looks_like_stock(v: &str) -> bool {
    let n = v.trim().to_uppercase();
    if n.is_empty() { return false; }
    if n.ends_with(".SZ")||n.ends_with(".SH")||n.ends_with(".BJ") {
        return n.split('.').next().map(|h| h.chars().all(|c|c.is_ascii_digit())).unwrap_or(false);
    }
    n.chars().all(|c| c.is_ascii_digit())
}
fn load_universe(f: Option<&Path>) -> Result<(Option<Vec<String>>, Option<std::collections::HashSet<String>>)> {
    let p = match f { Some(p)=>p, None=>return Ok((None,None)) };
    if !p.exists() { anyhow::bail!("not found: {}",p.display()); }
    let c_raw = fs::read_to_string(p)?;
    let c = c_raw.strip_prefix('\u{FEFF}').unwrap_or(&c_raw);
    let mut ord = Vec::new(); let mut set = std::collections::HashSet::new();
    for (i,l) in c.lines().enumerate() {
        let s = l.split(',').next().unwrap_or("").trim().to_string();
        if s.is_empty() { continue; }
        if i==0 && !looks_like_stock(&s) { continue; }
        let n = s.to_uppercase();
        if set.insert(n.clone()) { ord.push(n); }
    }
    Ok((Some(ord), Some(set)))
}
fn find_ref(d: &Path) -> Option<PathBuf> {
    for n in &["reference_features.csv","features.csv"] { let p=d.join(n); if p.exists(){return Some(p);} }
    None
}
fn filt(d: Vec<PathBuf>, u: &Option<std::collections::HashSet<String>>) -> Vec<PathBuf> {
    match u { Some(u)=>d.into_iter().filter(|d|u.contains(&d.file_name().unwrap().to_string_lossy().to_uppercase())).collect(), None=>d }
}
fn miss(d: &Path) -> Vec<String> {
    let mut m=Vec::new();
    if !d.join("\u{9010}\u{7b14}\u{6210}\u{4ea4}.csv").exists(){m.push("trades".into());}
    if !d.join("\u{9010}\u{7b14}\u{59d4}\u{6258}.csv").exists(){m.push("orders".into());}
    if !d.join("\u{884c}\u{60c5}.csv").exists(){m.push("snapshots".into());}
    m
}
fn rsec(v:f64)->f64{(v*1e6).round()/1e6}
fn dec(b:&[u8])->String{ match std::str::from_utf8(b){Ok(t)=>t.to_string(),Err(_)=>GB18030.decode(b).0.to_string()} }

fn scaled_price(val: f64) -> f64 {
    if val > 1000.0 { val / 10000.0 } else { val }
}

fn build_raw(sd: &Path) -> Result<HashMap<String, f64>> {
    let mut s = HashMap::new();

    // 1. Read quote rows
    let qp = sd.join("\u{884c}\u{60c5}.csv");
    let qb = fs::read(&qp)?;
    let qt = dec(&qb); let qt = qt.strip_prefix('\u{FEFF}').unwrap_or(&qt);
    let mut qr = ReaderBuilder::new().has_headers(true).from_reader(qt.as_bytes());
    let qh: Vec<String> = qr.headers()?.iter().map(|x| x.to_string()).collect();
    let qi: HashMap<&str,usize> = qh.iter().enumerate().map(|(i,h)|(h.as_str(),i)).collect();
    let qv = |r: &csv::StringRecord, n: &str| -> f64 {
        qi.get(n).and_then(|&i| r.get(i)).and_then(|v| v.parse::<f64>().ok()).unwrap_or(0.0)
    };

    struct QRow { time: f64, close: f64, open: f64, high: f64, low: f64, prev_close: f64,
        up: f64, down: f64, flat: f64,
        bid_vols: [f64; 10], ask_vols: [f64; 10] }

    let mut qrows: Vec<QRow> = Vec::new();
    for res in qr.records() {
        let r = match res { Ok(r)=>r, Err(_)=>continue };
        let mut bv = [0.0f64; 10]; let mut av = [0.0f64; 10];
        for i in 0..10 {
            bv[i] = qv(&r, &format!("\u{7533}\u{4e70}\u{91cf}{}", i+1));
            av[i] = qv(&r, &format!("\u{7533}\u{5356}\u{91cf}{}", i+1));
        }
        qrows.push(QRow {
            time: qv(&r, "\u{65f6}\u{95f4}"),
            close: scaled_price(qv(&r, "\u{6210}\u{4ea4}\u{4ef7}")),
            open: scaled_price(qv(&r, "\u{5f00}\u{76d8}\u{4ef7}")),
            high: scaled_price(qv(&r, "\u{6700}\u{9ad8}\u{4ef7}")),
            low: scaled_price(qv(&r, "\u{6700}\u{4f4e}\u{4ef7}")),
            prev_close: scaled_price(qv(&r, "\u{524d}\u{6536}\u{76d8}")),
            up: qv(&r, "\u{4e0a}\u{6da8}\u{54c1}\u{79cd}\u{6570}"),
            down: qv(&r, "\u{4e0b}\u{8dcc}\u{54c1}\u{79cd}\u{6570}"),
            flat: qv(&r, "\u{6301}\u{5e73}\u{54c1}\u{79cd}\u{6570}"),
            bid_vols: bv, ask_vols: av,
        });
    }

    let last_q = qrows.last();
    let prev_close = last_q.map(|q| q.prev_close).unwrap_or(0.0);
    let up_count = last_q.map(|q| q.up).unwrap_or(0.0) as i64;
    let down_count = last_q.map(|q| q.down).unwrap_or(0.0) as i64;
    let flat_count = last_q.map(|q| q.flat).unwrap_or(0.0) as i64;

    // bid/ask from last quote
    let (bid_vol, ask_vol) = if let Some(lq) = last_q {
        (lq.bid_vols.iter().sum::<f64>(), lq.ask_vols.iter().sum::<f64>())
    } else { (0.0, 0.0) };
    let total_liq = bid_vol + ask_vol;
    let bid_support = if total_liq > 0.0 { bid_vol / total_liq } else { 0.0 };
    let ask_pressure = if total_liq > 0.0 { ask_vol / total_liq } else { 0.0 };

    // Collect non-zero prices from quotes
    let nz_closes: Vec<f64> = qrows.iter().map(|q| q.close).filter(|&c| c > 0.0).collect();
    let nz_opens: Vec<f64> = qrows.iter().map(|q| q.open).filter(|&c| c > 0.0).collect();
    let nz_highs: Vec<f64> = qrows.iter().map(|q| q.high).filter(|&c| c > 0.0).collect();
    let nz_lows: Vec<f64> = qrows.iter().map(|q| q.low).filter(|&c| c > 0.0).collect();

    let close_price = nz_closes.last().copied().unwrap_or(0.0);
    let open_price = nz_opens.first().copied().unwrap_or(0.0);
    let high_price = nz_highs.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let high_price = if high_price == f64::NEG_INFINITY { close_price } else { high_price };
    let low_price = nz_lows.iter().copied().fold(f64::INFINITY, f64::min);
    let low_price = if low_price == f64::INFINITY { close_price } else { low_price };

    let price_impact = if prev_close > 0.0 && close_price > 0.0 {
        (close_price - prev_close).abs() / prev_close
    } else { 0.0 };

    let reference_open = if open_price > 0.0 { open_price } else { prev_close };
    let mut net_direction = 0.0;
    let mut close_return = 0.0;
    let mut open_return = 0.0;
    let mut intraday_range = 0.0;
    let mut close_strength = 0.0;

    if prev_close > 0.0 && close_price > 0.0 {
        net_direction = (close_price - reference_open) / prev_close;
        close_return = (close_price - prev_close) / prev_close;
        open_return = (reference_open - prev_close) / prev_close;
        if high_price > 0.0 && low_price > 0.0 {
            intraday_range = (high_price - low_price) / prev_close;
        }
    }
    if high_price > low_price && close_price > 0.0 {
        close_strength = (close_price - low_price) / (high_price - low_price);
    }

    // 2. Read trades
    let tp = sd.join("\u{9010}\u{7b14}\u{6210}\u{4ea4}.csv");
    let tb = fs::read(&tp)?;
    let tt = dec(&tb); let tt = tt.strip_prefix('\u{FEFF}').unwrap_or(&tt);
    let mut tr = ReaderBuilder::new().has_headers(true).from_reader(tt.as_bytes());
    let th: Vec<String> = tr.headers()?.iter().map(|x| x.to_string()).collect();
    let ti: HashMap<&str,usize> = th.iter().enumerate().map(|(i,h)|(h.as_str(),i)).collect();
    let tv_ = |r: &csv::StringRecord, n: &str| -> f64 {
        ti.get(n).and_then(|&i| r.get(i)).and_then(|v| v.parse::<f64>().ok()).unwrap_or(0.0)
    };

    let mut trade_amounts: Vec<f64> = Vec::new();
    let mut trade_times: Vec<i64> = Vec::new();
    let mut total_volume = 0.0f64;
    let mut bucket_amounts: HashMap<i64, f64> = HashMap::new();

    for res in tr.records() {
        let r = match res { Ok(r)=>r, Err(_)=>continue };
        let price = scaled_price(tv_(&r, "\u{6210}\u{4ea4}\u{4ef7}\u{683c}"));
        let volume = tv_(&r, "\u{6210}\u{4ea4}\u{6570}\u{91cf}");
        let time = tv_(&r, "\u{65f6}\u{95f4}") as i64;
        let amount = price * volume;
        trade_amounts.push(amount);
        trade_times.push(time);
        total_volume += volume;

        let hhmm = time / 100000;
        let bucket = if hhmm > 0 { hhmm / 5 } else { 0 };
        *bucket_amounts.entry(bucket).or_insert(0.0) += amount;
    }

    let total_trade_amount: f64 = trade_amounts.iter().sum();
    let tail_trade_amount: f64 = trade_amounts.iter().zip(trade_times.iter())
        .filter(|(_, &t)| t >= 143000000)
        .map(|(&a, _)| a)
        .sum();
    let avg_trade_size = if !trade_amounts.is_empty() {
        total_trade_amount / trade_amounts.len() as f64
    } else { 0.0 };

    let burst_ratio = if !bucket_amounts.is_empty() {
        let total_b: f64 = bucket_amounts.values().sum();
        if total_b > 0.0 {
            bucket_amounts.values().copied().fold(0.0f64, f64::max) / total_b
        } else { 0.0 }
    } else { 0.0 };

    let buy_amount = net_direction.max(0.0) * total_trade_amount;
    let sell_amount = (-net_direction).max(0.0) * total_trade_amount;
    let tail_ratio = if total_trade_amount > 0.0 { tail_trade_amount / total_trade_amount } else { 0.0 };

    // 3. Read orders
    let mut cancel_ratio = 0.0;
    let mut order_buy_ratio = 0.5;
    let mut order_count = 0usize;
    let op = sd.join("\u{9010}\u{7b14}\u{59d4}\u{6258}.csv");
    if op.exists() {
        if let Ok(ob) = fs::read(&op) {
            let ot = dec(&ob); let ot = ot.strip_prefix('\u{FEFF}').unwrap_or(&ot);
            let mut or_ = ReaderBuilder::new().has_headers(true).from_reader(ot.as_bytes());
            if let Ok(hd) = or_.headers() {
                let oh: Vec<String> = hd.iter().map(|x| x.to_string()).collect();
                let oi: HashMap<&str,usize> = oh.iter().enumerate().map(|(i,h)|(h.as_str(),i)).collect();
                let osv = |r: &csv::StringRecord, n: &str| -> String {
                    oi.get(n).and_then(|&i| r.get(i)).unwrap_or("").trim().to_string()
                };
                let mut cancel_like = 0usize;
                let mut buy_orders = 0usize;
                let mut sell_orders = 0usize;
                for res in or_.records() {
                    let r = match res { Ok(r)=>r, Err(_)=>continue };
                    order_count += 1;
                    let otype = osv(&r, "\u{59d4}\u{6258}\u{7c7b}\u{578b}");
                    let code = osv(&r, "\u{59d4}\u{6258}\u{4ee3}\u{7801}");
                    if !otype.is_empty() && otype != "0" { cancel_like += 1; }
                    if code == "B" { buy_orders += 1; }
                    if code == "S" { sell_orders += 1; }
                }
                cancel_ratio = if order_count > 0 { cancel_like as f64 / order_count as f64 } else { 0.0 };
                order_buy_ratio = if buy_orders + sell_orders > 0 {
                    buy_orders as f64 / (buy_orders + sell_orders) as f64
                } else { 0.5 };
            }
        }
    }

    // last15_return from quote rows
    let last15_prices: Vec<f64> = qrows.iter()
        .filter(|q| q.time >= 144500000.0 && q.close > 0.0)
        .map(|q| q.close)
        .collect();
    let last15_return = if last15_prices.len() >= 2 && prev_close > 0.0 {
        (last15_prices[last15_prices.len()-1] - last15_prices[0]) / prev_close
    } else { 0.0 };

    let directional_efficiency = if intraday_range > 0.0 {
        ((close_return - open_return).abs() / intraday_range).min(1.0)
    } else { 0.0 };
    let reversal_strength = close_return - open_return;

    s.insert("deal_amount".into(), total_trade_amount);
    s.insert("buy_amount".into(), buy_amount);
    s.insert("sell_amount".into(), sell_amount);
    s.insert("net_direction".into(), net_direction);
    s.insert("close_return".into(), close_return);
    s.insert("open_return".into(), open_return);
    s.insert("intraday_range".into(), intraday_range);
    s.insert("close_strength".into(), close_strength);
    s.insert("cancel_ratio".into(), cancel_ratio);
    s.insert("burst_ratio".into(), burst_ratio);
    s.insert("price_impact".into(), price_impact);
    s.insert("bid_support".into(), bid_support);
    s.insert("ask_pressure".into(), ask_pressure);
    s.insert("tail_ratio".into(), tail_ratio);
    s.insert("last15_return".into(), last15_return);
    s.insert("window_count".into(), bucket_amounts.len().max(1) as f64);
    s.insert("total_volume".into(), total_volume);
    s.insert("order_count".into(), order_count as f64);
    s.insert("trade_count".into(), trade_amounts.len() as f64);
    s.insert("avg_trade_size".into(), avg_trade_size);
    s.insert("order_buy_ratio".into(), order_buy_ratio);
    s.insert("directional_efficiency".into(), directional_efficiency);
    s.insert("reversal_strength".into(), reversal_strength);
    s.insert("up_count_market".into(), up_count as f64);
    s.insert("down_count_market".into(), down_count as f64);
    s.insert("flat_count_market".into(), flat_count as f64);
    Ok(s)
}

fn build_ref(_h: &[String], ci: &HashMap<&str,usize>, rows: impl Iterator<Item=csv::StringRecord>) -> HashMap<String,f64> {
    let gv = |r: &csv::StringRecord, ns: &[&str]| -> f64 {
        for n in ns { if let Some(&i)=ci.get(n){if let Some(v)=r.get(i){if let Ok(v)=v.parse::<f64>(){return v;}}} }
        0.0
    };
    let mut s=HashMap::new();
    let (mut ds,mut bs2,mut ss,mut cns,mut brs,mut bis,mut aks)=(0.0,0.0,0.0,0.0,0.0,0.0,0.0);
    let mut n=0u64; let mut fo=0.0; let mut lv=[0.0f64;13];
    for r in rows {
        if n==0{fo=gv(&r,&["open_return"]);}
        ds+=gv(&r,&["deal_amount","amount"]); bs2+=gv(&r,&["signal_deal_buy_amount","buy_amount"]);
        ss+=gv(&r,&["signal_deal_sell_amount","sell_amount"]);
        cns+=gv(&r,&["cb_cancel_order_ratio","cancel_ratio"]); brs+=gv(&r,&["rs_burst_ratio","burst_ratio"]);
        bis+=gv(&r,&["obp_at_best_bid_ratio","bid_support"]); aks+=gv(&r,&["obp_at_best_ask_ratio","ask_pressure"]);
        lv[0]=gv(&r,&["close_return","pct_change"]); lv[1]=gv(&r,&["open_return"]);
        lv[2]=gv(&r,&["intraday_range"]); lv[3]=gv(&r,&["close_strength"]);
        lv[4]=gv(&r,&["tail_ratio"]); lv[5]=gv(&r,&["last15_return"]);
        lv[6]=gv(&r,&["avg_trade_size"]); lv[7]=gv(&r,&["order_buy_ratio"]);
        lv[8]=gv(&r,&["directional_efficiency"]); lv[9]=gv(&r,&["reversal_strength"]);
        lv[10]=gv(&r,&["price_impact","pi_max_price_impact_pct"]); lv[11]=gv(&r,&["up_count_market","market_up_count"]);
        lv[12]=gv(&r,&["down_count_market","market_down_count"]);
        n+=1;
    }
    if n==0{return s;} let nf=n as f64;
    let nd=if ds>0.0{(bs2-ss)/ds}else{0.0};
    s.insert("deal_amount".into(),ds); s.insert("buy_amount".into(),bs2);
    s.insert("sell_amount".into(),ss); s.insert("net_direction".into(),nd);
    s.insert("cancel_ratio".into(),cns/nf); s.insert("burst_ratio".into(),brs/nf);
    s.insert("bid_support".into(),bis/nf); s.insert("ask_pressure".into(),aks/nf);
    s.insert("close_return".into(),lv[0]); s.insert("open_return".into(),fo);
    s.insert("intraday_range".into(),lv[2]); s.insert("close_strength".into(),lv[3]);
    s.insert("tail_ratio".into(),lv[4]); s.insert("last15_return".into(),lv[5]);
    s.insert("avg_trade_size".into(),lv[6]);
    s.insert("order_buy_ratio".into(),if lv[7]!=0.0{lv[7]}else{0.5});
    s.insert("directional_efficiency".into(),lv[8]); s.insert("reversal_strength".into(),lv[9]);
    s.insert("price_impact".into(),lv[10]); s.insert("up_count_market".into(),lv[11]);
    s.insert("down_count_market".into(),lv[12]);
    s
}

fn load_samples(inp: &Path, td: &str, sl: Option<usize>, so: usize, su: &Option<std::collections::HashSet<String>>)
    -> (Vec<DailySample>, HashMap<String,Vec<String>>, Vec<HashMap<String,f64>>)
{
    let mut smp=Vec::new(); let mut inc=HashMap::new(); let mut stm=Vec::new();
    if let Some(rf)=find_ref(inp) {
        if let Ok(b)=fs::read(&rf) {
            let t=dec(&b); let t=t.strip_prefix('\u{FEFF}').unwrap_or(&t);
            let mut rdr=ReaderBuilder::new().has_headers(true).from_reader(t.as_bytes());
            if let Ok(hd)=rdr.headers() {
                let hdr: Vec<String>=hd.iter().map(|x|x.to_string()).collect();
                let ci: HashMap<&str,usize>=hdr.iter().enumerate().map(|(i,h)|(h.as_str(),i)).collect();
                let si=ci.get("symbol").or_else(||ci.get("stock_code")).copied();
                let di=ci.get("date").or_else(||ci.get("transaction_date")).copied();
                if let Some(si)=si {
                    let mut sym: HashMap<String,Vec<csv::StringRecord>>=HashMap::new();
                    for res in rdr.records() {
                        let r=match res{Ok(r)=>r,Err(_)=>continue};
                        if let Some(di)=di{if let Some(d)=r.get(di){if !d.is_empty()&&!d.contains(td){continue;}}}
                        if let Some(s)=r.get(si){if !s.is_empty(){sym.entry(s.to_uppercase()).or_default().push(r.clone());}}
                    }
                    let mut keys: Vec<String>=sym.keys().cloned().collect(); keys.sort();
                    if let Some(u)=su{keys.retain(|s|u.contains(s));}
                    let keys: Vec<String>=keys.into_iter().skip(so).take(sl.unwrap_or(usize::MAX)).collect();
                    for k in &keys {
                        let st=Instant::now(); let rows=sym.remove(k).unwrap_or_default();
                        if rows.is_empty(){continue;}
                        let sm=build_ref(&hdr,&ci,rows.into_iter()); if sm.is_empty(){continue;}
                        let el=st.elapsed().as_secs_f64();
                        smp.push(DailySample{stock_code:k.clone(),transaction_date:td.into(),rows:Vec::new(),feature_summary:sm,quality_flags:HashMap::new()});
                        let mut t2=HashMap::new(); t2.insert("sample_build_seconds".into(),rsec(el)); stm.push(t2);
                    }
                }
            }
        }
        return (smp,inc,stm);
    }
    let sd=filt(iter_stock_dirs(inp),su);
    for d in sd.iter().skip(so).take(sl.unwrap_or(usize::MAX)) {
        let ms=miss(d);
        if !ms.is_empty(){inc.insert(d.file_name().unwrap().to_string_lossy().to_string(),ms);continue;}
        let st=Instant::now();
        let sym=d.file_name().unwrap().to_string_lossy().to_uppercase();
        let sm=match build_raw(d){Ok(s) if !s.is_empty()=>s, _=>{inc.insert(sym.clone(),vec!["no_data".into()]);continue;}};
        let el=st.elapsed().as_secs_f64();
        smp.push(DailySample{stock_code:sym,transaction_date:td.into(),rows:Vec::new(),feature_summary:sm,quality_flags:HashMap::new()});
        let mut t2=HashMap::new(); t2.insert("sample_build_seconds".into(),rsec(el)); stm.push(t2);
    }
    (smp,inc,stm)
}

fn sort_ord<T>(r: &mut [T], req: &Option<Vec<String>>, kf: impl Fn(&T)->String) {
    if let Some(o)=req {
        let m: HashMap<String,usize>=o.iter().enumerate().map(|(i,s)|(s.clone(),i)).collect();
        r.sort_by_key(|i|m.get(&kf(i).to_uppercase()).copied().unwrap_or(usize::MAX));
    }
}

pub fn run_daily_batch(td: &str, inp: &Path, out: &Path, cfg: &ConfigMap, ld: &ConfigMap,
    sl: Option<usize>, so: usize, slf: Option<&Path>, zip: bool, prof: bool)
    -> Result<HashMap<String,serde_json::Value>>
{
    let t0=Instant::now(); fs::create_dir_all(out)?;
    let (req,su)=load_universe(slf)?;
    let mut w: Vec<String>=Vec::new(); let mut ms=0.0f64;
    let t1=Instant::now();
    let (mut smp,inc,stm)=load_samples(inp,td,sl,so,&su);
    let sbs=t1.elapsed().as_secs_f64();
    if smp.is_empty(){w.push("No samples.".into());}
    let t1=Instant::now();
    let mut pr: Vec<PatternResult>=smp.iter().map(|s|predict_pattern(s,cfg,ld)).collect();
    let ps=t1.elapsed().as_secs_f64();
    let t1=Instant::now();
    let mut pd: Vec<PredictResult>=smp.iter().map(|s|predict_capital(s,cfg,ld)).collect();
    let cps=t1.elapsed().as_secs_f64();
    let mut msn: Option<MarketPidSnapshot>=None;
    if !smp.is_empty()&&get_bool(cfg,"enable_market_snapshot",true) {
        let t1=Instant::now();
        msn=Some(estimate_market_pid(&mut smp,&pr,&pd,cfg));
        if let Some(ref sn)=msn{attach_market_relative_metrics(&smp,&mut pd,sn);}
        ms=t1.elapsed().as_secs_f64();
    }
    if let Some(ref rq)=req {
        let act: std::collections::HashSet<String>=smp.iter().map(|s|s.stock_code.to_uppercase()).collect();
        let mi: Vec<String>=rq.iter().filter(|s|!act.contains(&s.to_uppercase())).cloned().collect();
        if !mi.is_empty(){w.push(format!("Missing: {}",mi.join(", ")));}
    }
    if !inc.is_empty(){
        let mut d: Vec<String>=inc.iter().map(|(s,f)|format!("{}({})",s,f.join(","))).collect();
        d.sort(); w.push(format!("Skipped: {}",d.join("; ")));
    }
    sort_ord(&mut pr,&req,|r|r.stock_code.clone());
    sort_ord(&mut pd,&req,|r|r.stock_code.clone());
    let t1=Instant::now();
    exporter::export_pattern_reco(&pr,&out.join("pattern_reco.csv"))?;
    exporter::export_predict_result(&pd,&out.join("predict_result.csv"))?;
    let (dj,dc)=exporter::export_batch_diagnostics(msn.as_ref(),&pr,&pd,out)?;
    let mut msp: Option<String>=None; let mut mrp: Option<String>=None;
    if let Some(ref sn)=msn {
        let sp=out.join("market_pid_snapshot.csv"); let rp=out.join("market_regime_report.md");
        exporter::export_market_pid_snapshot(sn,&sp)?; exporter::export_market_regime_report(sn,&rp)?;
        msp=Some(sp.to_string_lossy().to_string()); mrp=Some(rp.to_string_lossy().to_string());
    }
    let mut es=t1.elapsed().as_secs_f64();
    let mut sz: Option<String>=None;
    if zip {
        let t1=Instant::now();
        match exporter::build_submit_zip(out){Ok(p)=>sz=Some(p),Err(e)=>w.push(format!("zip: {}",e))}
        es+=t1.elapsed().as_secs_f64();
    }
    let mut psm: Option<serde_json::Value>=None;
    if prof {
        let ts=t0.elapsed().as_secs_f64();
        let top: Vec<serde_json::Value>=stm.iter().rev().take(20).map(|t|{
            let mut m=serde_json::Map::new();
            m.insert("sample_build_seconds".into(),serde_json::json!(rsec(*t.get("sample_build_seconds").unwrap_or(&0.0))));
            serde_json::Value::Object(m)
        }).collect();
        let mut p=serde_json::Map::new();
        p.insert("total_seconds".into(),serde_json::json!(rsec(ts)));
        p.insert("sample_build_seconds".into(),serde_json::json!(rsec(sbs)));
        p.insert("pattern_seconds".into(),serde_json::json!(rsec(ps)));
        p.insert("capital_seconds".into(),serde_json::json!(rsec(cps)));
        p.insert("market_seconds".into(),serde_json::json!(rsec(ms)));
        p.insert("export_seconds".into(),serde_json::json!(rsec(es)));
        p.insert("processed_samples".into(),serde_json::json!(smp.len()));
        p.insert("skipped".into(),serde_json::json!(inc.len()));
        p.insert("top_slowest".into(),serde_json::Value::Array(top));
        psm=Some(serde_json::Value::Object(p));
    }
    let mut r=HashMap::new();
    r.insert("trade_date".into(),serde_json::Value::String(td.into()));
    r.insert("sample_count".into(),serde_json::json!(smp.len()));
    r.insert("output_count".into(),serde_json::json!(pr.len()));
    r.insert("warnings".into(),serde_json::Value::Array(w.iter().map(|w|serde_json::Value::String(w.clone())).collect()));
    if let Some(z)=sz{r.insert("submit_zip".into(),serde_json::Value::String(z));}
    if let Some(p)=msp{r.insert("market_snapshot_path".into(),serde_json::Value::String(p));}
    if let Some(p)=mrp{r.insert("market_report_path".into(),serde_json::Value::String(p));}
    r.insert("diagnostics_json_path".into(),serde_json::Value::String(dj));
    r.insert("distribution_csv_path".into(),serde_json::Value::String(dc));
    if let Some(p)=psm{r.insert("performance_summary".into(),p);}
    Ok(r)
}
