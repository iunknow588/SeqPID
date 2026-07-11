use std::collections::{HashMap, VecDeque};

#[derive(Debug, Clone)]
struct OrderState {
    order_id: String,
    order_time_seconds: i32,
    remaining_volume: f64,
}

#[derive(Debug, Clone)]
struct LifecycleEvent {
    time_seconds: i32,
    event_order: i32,
    order_id: String,
    side: String,
    price_key: String,
    volume: f64,
    event_type: String,
}

#[derive(Debug, Clone, Default)]
pub struct OrderAgeResult {
    pub order_age_minutes: Option<f64>,
    pub recovery_method: String,
}

pub fn time_value_to_seconds(raw_time: &str) -> Option<i32> {
    let value = to_float(raw_time, 0.0) as i64;
    if value <= 0 {
        return None;
    }
    let hhmmss = if value > 235_959 { value / 1000 } else { value };
    let hh = hhmmss / 10_000;
    let mm = (hhmmss % 10_000) / 100;
    let ss = hhmmss % 100;
    if hh > 23 || mm > 59 || ss > 59 {
        return None;
    }
    Some((hh * 3600 + mm * 60 + ss) as i32)
}

pub struct OrderLifecycleResolver {
    events: Vec<LifecycleEvent>,
    event_index: usize,
    orders: Vec<OrderState>,
    orders_by_id: HashMap<String, usize>,
    queues: HashMap<(String, String), VecDeque<usize>>,
}

impl OrderLifecycleResolver {
    pub fn new(order_rows: &[HashMap<String, String>], trade_rows: &[HashMap<String, String>]) -> Self {
        let mut events = build_order_events(order_rows);
        events.extend(build_trade_cancel_events(trade_rows));
        events.sort_by_key(|item| (item.time_seconds, item.event_order));
        Self {
            events,
            event_index: 0,
            orders: Vec::new(),
            orders_by_id: HashMap::new(),
            queues: HashMap::new(),
        }
    }

    pub fn lookup_order_age_minutes(
        &mut self,
        trade_row: &HashMap<String, String>,
        trade_time_seconds: Option<i32>,
        active_sign: i32,
        side_sign: i32,
        trade_price: f64,
        trade_volume: f64,
    ) -> OrderAgeResult {
        let trade_time_seconds = match trade_time_seconds {
            Some(value) => value,
            None => {
                return OrderAgeResult {
                    order_age_minutes: None,
                    recovery_method: "missing_trade_time".to_string(),
                }
            }
        };

        self.advance_to(trade_time_seconds);
        let passive_side = trade_passive_side(active_sign, side_sign);
        if passive_side.is_empty() {
            return OrderAgeResult {
                order_age_minutes: None,
                recovery_method: "passive_side_unresolved".to_string(),
            };
        }

        let passive_order_id = trade_passive_order_id(trade_row, passive_side);
        if !passive_order_id.is_empty() {
            if let Some(&index) = self.orders_by_id.get(&passive_order_id) {
                let age = (trade_time_seconds - self.orders[index].order_time_seconds) as f64 / 60.0;
                self.consume_order(index, trade_volume);
                return OrderAgeResult {
                    order_age_minutes: Some(age),
                    recovery_method: "direct_order_id".to_string(),
                };
            }
        }

        if let Some(index) = self.consume_fifo(passive_side, &price_key_f64(trade_price), trade_volume) {
            let age = (trade_time_seconds - self.orders[index].order_time_seconds) as f64 / 60.0;
            return OrderAgeResult {
                order_age_minutes: Some(age),
                recovery_method: "fifo_price_queue".to_string(),
            };
        }

        OrderAgeResult {
            order_age_minutes: None,
            recovery_method: "order_lifecycle_unresolved".to_string(),
        }
    }

    fn advance_to(&mut self, trade_time_seconds: i32) {
        while self.event_index < self.events.len()
            && self.events[self.event_index].time_seconds <= trade_time_seconds
        {
            let event = self.events[self.event_index].clone();
            self.event_index += 1;
            if event.event_type == "delete" {
                self.delete_event(event);
            } else {
                self.add_event(event);
            }
        }
    }

    fn add_event(&mut self, event: LifecycleEvent) {
        let index = self.orders.len();
        let order = OrderState {
            order_id: event.order_id.clone(),
            order_time_seconds: event.time_seconds,
            remaining_volume: event.volume,
        };
        self.orders.push(order);
        if !event.order_id.is_empty() {
            self.orders_by_id.insert(event.order_id, index);
        }
        self.queues
            .entry((event.side, event.price_key))
            .or_default()
            .push_back(index);
    }

    fn delete_event(&mut self, event: LifecycleEvent) {
        if !event.order_id.is_empty() {
            if let Some(&index) = self.orders_by_id.get(&event.order_id) {
                self.consume_order(index, event.volume);
                return;
            }
        }
        if !event.side.is_empty() && !event.price_key.is_empty() {
            let _ = self.consume_fifo(&event.side, &event.price_key, event.volume);
        }
    }

    fn consume_order(&mut self, index: usize, volume: f64) {
        let used = volume.max(0.0);
        if let Some(order) = self.orders.get_mut(index) {
            order.remaining_volume -= used;
            if order.remaining_volume <= 0.0 && !order.order_id.is_empty() {
                self.orders_by_id.remove(&order.order_id);
            }
        }
    }

    fn consume_fifo(&mut self, side: &str, pkey: &str, volume: f64) -> Option<usize> {
        let key = (side.to_string(), pkey.to_string());
        let queue = self.queues.get_mut(&key)?;
        let mut remaining = volume.max(0.0);
        let mut first_consumed: Option<usize> = None;
        while let Some(&index) = queue.front() {
            if self.orders[index].remaining_volume <= 0.0 {
                queue.pop_front();
                continue;
            }
            if first_consumed.is_none() {
                first_consumed = Some(index);
            }
            let used = self.orders[index].remaining_volume.min(remaining);
            self.orders[index].remaining_volume -= used;
            remaining -= used;
            if self.orders[index].remaining_volume <= 0.0 {
                queue.pop_front();
                let order_id = self.orders[index].order_id.clone();
                if !order_id.is_empty() {
                    self.orders_by_id.remove(&order_id);
                }
            }
            if remaining <= 0.0 {
                break;
            }
        }
        first_consumed
    }
}

fn build_order_events(rows: &[HashMap<String, String>]) -> Vec<LifecycleEvent> {
    let mut events = Vec::new();
    for row in rows {
        let time_seconds = pick_names(row, &["\u{65f6}\u{95f4}", "order_time", "time", "timestamp_ms"])
            .and_then(time_value_to_seconds);
        let Some(time_seconds) = time_seconds else { continue; };
        let order_id = pick_text(
            row,
            &[
                "\u{4ea4}\u{6613}\u{6240}\u{59d4}\u{6258}\u{53f7}",
                "order_id",
                "exchange_order_id",
            ],
        );
        let side = normalize_side(pick_names(row, &["\u{59d4}\u{6258}\u{4ee3}\u{7801}", "side"]));
        let pkey = price_key_str(pick_names(row, &["\u{59d4}\u{6258}\u{4ef7}\u{683c}", "price"]));
        let volume = pick_names(row, &["\u{59d4}\u{6258}\u{6570}\u{91cf}", "volume"])
            .map(|value| to_float(value, 0.0))
            .unwrap_or(0.0);
        let event_type = normalize_order_type(pick_names(row, &["\u{59d4}\u{6258}\u{7c7b}\u{578b}", "order_type"]));
        if volume <= 0.0 {
            continue;
        }
        if event_type == "add" && (side.is_empty() || pkey.is_empty()) {
            continue;
        }
        if event_type == "delete" && order_id.is_empty() && (side.is_empty() || pkey.is_empty()) {
            continue;
        }
        events.push(LifecycleEvent {
            time_seconds,
            event_order: 0,
            order_id,
            side,
            price_key: pkey,
            volume,
            event_type,
        });
    }
    events
}

fn build_trade_cancel_events(rows: &[HashMap<String, String>]) -> Vec<LifecycleEvent> {
    let mut events = Vec::new();
    for row in rows {
        if !is_cancel_trade(row) {
            continue;
        }
        let time_seconds = pick_names(row, &["\u{65f6}\u{95f4}", "time", "timestamp_ms"])
            .and_then(time_value_to_seconds);
        let Some(time_seconds) = time_seconds else { continue; };
        let buy_order_id = pick_text(row, &["\u{53eb}\u{4e70}\u{5e8f}\u{53f7}", "bid_order_id", "buy_order_id"]);
        let sell_order_id = pick_text(row, &["\u{53eb}\u{5356}\u{5e8f}\u{53f7}", "ask_order_id", "sell_order_id"]);
        let (order_id, side) = if !buy_order_id.is_empty() {
            (buy_order_id, "buy".to_string())
        } else if !sell_order_id.is_empty() {
            (sell_order_id, "sell".to_string())
        } else {
            (
                String::new(),
                normalize_side(pick_names(row, &["\u{59d4}\u{6258}\u{4ee3}\u{7801}", "side"])),
            )
        };
        let pkey = price_key_str(pick_names(row, &["\u{6210}\u{4ea4}\u{4ef7}\u{683c}", "price"]));
        let volume = pick_names(row, &["\u{6210}\u{4ea4}\u{6570}\u{91cf}", "volume"])
            .map(|value| to_float(value, 0.0))
            .unwrap_or(0.0);
        if volume <= 0.0 || (order_id.is_empty() && (side.is_empty() || pkey.is_empty())) {
            continue;
        }
        events.push(LifecycleEvent {
            time_seconds,
            event_order: 1,
            order_id,
            side,
            price_key: pkey,
            volume,
            event_type: "delete".to_string(),
        });
    }
    events
}

fn trade_passive_side(active_sign: i32, side_sign: i32) -> &'static str {
    if active_sign > 0 || (active_sign == 0 && side_sign > 0) {
        "sell"
    } else if active_sign < 0 || (active_sign == 0 && side_sign < 0) {
        "buy"
    } else {
        ""
    }
}

fn trade_passive_order_id(row: &HashMap<String, String>, passive_side: &str) -> String {
    match passive_side {
        "sell" => pick_text(row, &["\u{53eb}\u{5356}\u{5e8f}\u{53f7}", "ask_order_id", "sell_order_id"]),
        "buy" => pick_text(row, &["\u{53eb}\u{4e70}\u{5e8f}\u{53f7}", "bid_order_id", "buy_order_id"]),
        _ => String::new(),
    }
}

fn is_cancel_trade(row: &HashMap<String, String>) -> bool {
    normalize_order_type(pick_names(row, &["\u{6210}\u{4ea4}\u{4ee3}\u{7801}", "trade_type", "exec_type"])) == "delete"
}

fn normalize_side(value: Option<&str>) -> String {
    let raw = value.unwrap_or("").trim().to_uppercase();
    if matches!(raw.as_str(), "B" | "BUY" | "1") {
        "buy".to_string()
    } else if matches!(raw.as_str(), "S" | "SELL" | "2") {
        "sell".to_string()
    } else {
        String::new()
    }
}

fn normalize_order_type(value: Option<&str>) -> String {
    let raw = value.unwrap_or("").trim().to_uppercase();
    if matches!(raw.as_str(), "D" | "C" | "CANCEL" | "DELETE") || raw.contains('\u{64a4}') {
        "delete".to_string()
    } else {
        "add".to_string()
    }
}

fn pick_names<'a>(row: &'a HashMap<String, String>, names: &[&str]) -> Option<&'a str> {
    names.iter().find_map(|name| {
        row.get(*name)
            .map(|value| value.trim())
            .filter(|value| !value.is_empty())
    })
}

fn pick_text(row: &HashMap<String, String>, names: &[&str]) -> String {
    pick_names(row, names)
        .filter(|value| *value != "0" && *value != "0.0")
        .unwrap_or("")
        .to_string()
}

fn to_float(value: &str, default: f64) -> f64 {
    value.parse::<f64>().unwrap_or(default)
}

fn price_key_str(value: Option<&str>) -> String {
    let raw = value.map(|v| to_float(v, 0.0)).unwrap_or(0.0);
    price_key_f64(raw)
}

fn price_key_f64(mut value: f64) -> String {
    if value == 0.0 {
        return String::new();
    }
    if value.abs() > 1000.0 {
        value /= 10000.0;
    }
    if (value - value.round()).abs() < 1e-9 {
        format!("{}", value.round() as i64)
    } else {
        let mut text = format!("{:.6}", value);
        while text.ends_with('0') {
            text.pop();
        }
        if text.ends_with('.') {
            text.pop();
        }
        text
    }
}
