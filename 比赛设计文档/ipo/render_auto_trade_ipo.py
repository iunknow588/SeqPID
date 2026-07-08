from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


CANVAS_SIZE = (2400, 1400)


def default_output_path() -> Path:
    return Path(__file__).resolve().parent / "比赛系统IPO总图.png"


def pick_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_dir = Path("C:/Windows/Fonts")
    names = (
        ["msyhbd.ttc", "simhei.ttf", "msyh.ttc", "simsun.ttc"]
        if bold
        else ["msyh.ttc", "simhei.ttf", "simsun.ttc"]
    )
    for name in names:
        path = font_dir / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def lerp_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(a[0] * (1 - t) + b[0] * t),
        int(a[1] * (1 - t) + b[1] * t),
        int(a[2] * (1 - t) + b[2] * t),
    )


def draw_background(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for y in range(height):
        t = y / max(height - 1, 1)
        draw.line((0, y, width, y), fill=lerp_color((8, 14, 26), (15, 34, 46), t))

    for x in range(-220, width, 160):
        draw.line((x, 0, x + 320, height), fill=(28, 66, 80), width=1)
    for y in range(120, height, 120):
        draw.line((0, y, width, y), fill=(24, 51, 63), width=1)

    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((1450, -150, 2500, 760), fill=(41, 126, 161, 56))
    glow_draw.ellipse((-260, 780, 820, 1460), fill=(58, 152, 122, 42))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(58)))


def rounded(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: str | tuple[int, int, int, int],
    outline: str | tuple[int, int, int, int],
    width: int = 2,
    radius: int = 24,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    if not text:
        return 0, 0
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for ch in paragraph:
            trial = current + ch
            if text_size(draw, trial, font)[0] <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = ch
        if current:
            lines.append(current)
    return lines


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_gap: int = 5,
) -> int:
    x, y = xy
    lines = wrap_text(draw, text, font, max_width)
    line_height = text_size(draw, "中文Ag", font)[1] + 4
    for i, line in enumerate(lines):
        draw.text((x, y + i * (line_height + line_gap)), line, font=font, fill=fill)
    return len(lines) * line_height + max(0, len(lines) - 1) * line_gap


def draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    color: str,
    width: int = 6,
) -> None:
    draw.line((start, end), fill=color, width=width)
    x1, y1 = start
    x2, y2 = end
    angle = math.atan2(y2 - y1, x2 - x1)
    length = 18
    spread = 0.56
    p1 = (x2, y2)
    p2 = (int(x2 - length * math.cos(angle - spread)), int(y2 - length * math.sin(angle - spread)))
    p3 = (int(x2 - length * math.cos(angle + spread)), int(y2 - length * math.sin(angle + spread)))
    draw.polygon((p1, p2, p3), fill=color)


def draw_column_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    tag: str,
    title: str,
    subtitle: str,
    items: list[str],
    accent: str,
    fonts: dict[str, ImageFont.ImageFont],
    colors: dict[str, str],
) -> None:
    x1, y1, x2, y2 = box
    rounded(draw, box, fill=colors["panel"], outline=accent, width=3, radius=28)
    draw.rounded_rectangle((x1 + 24, y1 + 20, x1 + 120, y1 + 56), radius=16, fill=accent)
    draw.text((x1 + 46, y1 + 26), tag, font=fonts["tag"], fill=colors["ink"])
    draw.text((x1 + 24, y1 + 82), title, font=fonts["card_title"], fill=colors["white"])
    draw_text_block(
        draw,
        (x1 + 24, y1 + 124),
        subtitle,
        font=fonts["body"],
        fill=colors["muted2"],
        max_width=x2 - x1 - 48,
        line_gap=4,
    )

    current_y = y1 + 194
    for item in items:
        draw.ellipse((x1 + 28, current_y + 10, x1 + 40, current_y + 22), fill=accent)
        used = draw_text_block(
            draw,
            (x1 + 56, current_y),
            item,
            font=fonts["body"],
            fill=colors["muted"],
            max_width=x2 - x1 - 84,
            line_gap=4,
        )
        current_y += used + 18

    info_box = (x1 + 22, y2 - 110, x2 - 22, y2 - 22)
    rounded(draw, info_box, fill=colors["chip"], outline=accent, width=2, radius=18)
    draw.text((x1 + 38, y2 - 98), "关键口径", font=fonts["mini_bold"], fill=colors["white"])
    info_text = {
        "I": "输入对象为交易日、配置、股票清单、逐笔成交/逐笔委托/行情或参考特征文件。",
        "P": "当前主链路为日级摘要特征 + Task1/Task2 基线评分 + 市场 PID 聚合。",
        "O": "输出比赛 CSV、市场快照、诊断文件与 submit.zip。",
    }[tag]
    draw_text_block(
        draw,
        (x1 + 38, y2 - 66),
        info_text,
        font=fonts["mini"],
        fill=colors["muted"],
        max_width=x2 - x1 - 76,
        line_gap=3,
    )


def draw_formula_chip(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    title: str,
    body: str,
    accent: str,
    fonts: dict[str, ImageFont.ImageFont],
    colors: dict[str, str],
) -> None:
    x1, y1, x2, y2 = box
    rounded(draw, box, fill=colors["formula"], outline=colors["formula_line"], width=2, radius=20)
    draw.rounded_rectangle((x1 + 18, y1 + 18, x1 + 24, y2 - 18), radius=3, fill=accent)
    draw.text((x1 + 42, y1 + 16), title, font=fonts["chip_title"], fill=colors["white"])
    draw_text_block(
        draw,
        (x1 + 42, y1 + 50),
        body,
        font=fonts["mini"],
        fill=colors["muted"],
        max_width=x2 - x1 - 60,
        line_gap=3,
    )


def render(output_path: Path) -> None:
    image = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 255))
    draw_background(image)
    draw = ImageDraw.Draw(image)

    fonts = {
        "title": pick_font(64, bold=True),
        "subtitle": pick_font(28),
        "section": pick_font(30, bold=True),
        "tag": pick_font(24, bold=True),
        "card_title": pick_font(34, bold=True),
        "body": pick_font(22),
        "chip_title": pick_font(24, bold=True),
        "mini": pick_font(19),
        "mini_bold": pick_font(19, bold=True),
        "footer": pick_font(20),
    }

    colors = {
        "ink": "#08111d",
        "white": "#f5fbff",
        "muted": "#c9dce6",
        "muted2": "#9eb8c7",
        "panel": "#0f2435",
        "chip": "#122b3c",
        "formula": "#10293a",
        "formula_line": "#365f73",
        "cyan": "#64e0cf",
        "blue": "#72b9ff",
        "amber": "#f3c560",
        "green": "#8be192",
        "rose": "#ef93a8",
        "line": "#79d3e3",
    }

    draw.text((82, 66), "自动化交易比赛系统 IPO 总图", font=fonts["title"], fill=colors["white"])
    draw.text(
        (88, 148),
        "基于当前代码实现与设计文档联合整理：输入定义准确、处理链路可追踪、输出口径可交付。",
        font=fonts["subtitle"],
        fill=colors["muted"],
    )

    input_items = [
        "控制输入：mode、date、input_dir、output_dir、stock_list_file、build_zip。",
        "配置输入：dev.yaml、label_dict.yaml，控制阈值、标签压缩模式、市场快照导出。",
        "数据输入 A：逐笔成交.csv、逐笔委托.csv、行情.csv。",
        "数据输入 B：reference_features.csv / features.csv / 参考特征.csv。",
        "样本粒度：股票-交易日；支持按股票目录或参考特征文件两种装载方式。",
    ]
    process_items = [
        "main.py 解析参数，scheduler.run_daily_batch 创建批次输出目录。",
        "样本装载后构造 DailySample.feature_summary。",
        "日级摘要特征：deal_amount、close_return、intraday_range、tail_ratio、order_buy_ratio、cancel_ratio 等。",
        "Task1：显式规则 + 候选标签评分 + 低置信回退，输出 pattern_type。",
        "Task2：散户/游资/量化三类评分，映射资金意图并压缩为提交标签。",
        "市场 PID：按股票计算 P/I/D，再做横截面聚合与 regime 判定。",
    ]
    output_items = [
        "标准输出：pattern_reco.csv。",
        "标准输出：predict_result.csv。",
        "辅助输出：market_pid_snapshot.csv、market_regime_report.md。",
        "诊断输出：batch_diagnostics.json、label_distribution.csv。",
        "交付输出：submit.zip，且校验 CSV 表头、字段数、空值与行数一致性。",
    ]

    draw_column_card(
        draw,
        (72, 250, 742, 960),
        tag="I",
        title="Input 输入",
        subtitle="系统接收控制参数、配置字典、股票清单与日终原始数据或参考特征文件。",
        items=input_items,
        accent=colors["cyan"],
        fonts=fonts,
        colors=colors,
    )
    draw_column_card(
        draw,
        (866, 250, 1536, 960),
        tag="P",
        title="Process 处理",
        subtitle="当前比赛链路是日终批处理基线系统，以日级摘要特征驱动模式识别、资金识别和市场聚合。",
        items=process_items,
        accent=colors["blue"],
        fonts=fonts,
        colors=colors,
    )
    draw_column_card(
        draw,
        (1660, 250, 2330, 960),
        tag="O",
        title="Output 输出",
        subtitle="系统导出比赛提交文件、市场快照和诊断产物，并在末端进行格式校验与打包。",
        items=output_items,
        accent=colors["amber"],
        fonts=fonts,
        colors=colors,
    )

    draw_arrow(draw, (742, 604), (866, 604), color=colors["line"], width=7)
    draw_arrow(draw, (1536, 604), (1660, 604), color=colors["line"], width=7)

    draw.text((86, 1022), "关键变换公式", font=fonts["section"], fill=colors["white"])

    formula_boxes = [
        (
            (72, 1074, 620, 1312),
            "日级摘要特征",
            "close_return = (close_price - prev_close) / prev_close\n"
            "intraday_range = (high_price - low_price) / prev_close\n"
            "tail_ratio = tail_trade_amount / total_trade_amount\n"
            "directional_efficiency = min(abs(close_return - open_return) / intraday_range, 1)",
            colors["green"],
        ),
        (
            (652, 1074, 1200, 1312),
            "Task1 模式识别",
            "先执行强规则识别，再对候选模式做线性加权评分。\n"
            "若最高分 < low_conf_threshold 或与第二名分差不足，则回退到规则标签。\n"
            "本质是可解释特征到交易模式标签的显式映射。",
            colors["rose"],
        ),
        (
            (1232, 1074, 1780, 1312),
            "Task2 资金识别",
            "capital_type = argmax(retail_score, hot_money_score, quant_score)\n"
            "capital_confidence = clamp(0.55 + margin / 1.5, 0, 1)\n"
            "细粒度资金意图再压缩为 买入 / 卖出 / 中性 / T0交易。",
            colors["cyan"],
        ),
        (
            (1812, 1074, 2360, 1312),
            "市场 PID 聚合",
            "P = 0.6*net_direction + 0.25*min(price_impact/0.02,1) + 0.15*tail_ratio\n"
            "I = 0.55*burst_ratio + 0.25*max(net_direction,0) + 0.20*tail_ratio\n"
            "D = 0.50*cancel_ratio + 0.30*max(ask_pressure-bid_support,0) + 0.20*(1-abs(net_direction))",
            colors["amber"],
        ),
    ]
    for box, title, body, accent in formula_boxes:
        draw_formula_chip(draw, box, title=title, body=body, accent=accent, fonts=fonts, colors=colors)

    draw.text(
        (84, 1350),
        "说明：当前图反映比赛系统真实主链路；KF / RTS / EWMA 等状态空间增强能力属于设计目标扩展链路，尚未正式接入比赛提交主流程。",
        font=fonts["footer"],
        fill=colors["muted2"],
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output_path, quality=96)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render automated trading IPO overview diagram")
    parser.add_argument("--output", type=Path, default=default_output_path())
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    render(args.output.resolve())
    print(f"IPO diagram written to: {args.output.resolve()}")


if __name__ == "__main__":
    main()
