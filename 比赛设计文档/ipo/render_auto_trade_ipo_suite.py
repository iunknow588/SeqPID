from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


CANVAS_SIZE = (2400, 1400)


def output_dir() -> Path:
    return Path(__file__).resolve().parent


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


def base_fonts() -> dict[str, ImageFont.ImageFont]:
    return {
        "title": pick_font(62, bold=True),
        "subtitle": pick_font(27),
        "section": pick_font(29, bold=True),
        "tag": pick_font(22, bold=True),
        "card_title": pick_font(31, bold=True),
        "body": pick_font(21),
        "mini": pick_font(19),
        "mini_bold": pick_font(19, bold=True),
        "footer": pick_font(19),
    }


def palette() -> dict[str, str]:
    return {
        "ink": "#08111d",
        "white": "#f5fbff",
        "muted": "#c9dce6",
        "muted2": "#9eb8c7",
        "panel": "#0f2435",
        "chip": "#122b3c",
        "line": "#79d3e3",
        "cyan": "#64e0cf",
        "blue": "#72b9ff",
        "amber": "#f3c560",
        "green": "#8be192",
        "rose": "#ef93a8",
        "violet": "#b89dff",
    }


def make_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw, dict[str, ImageFont.ImageFont], dict[str, str]]:
    image = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 255))
    draw_background(image)
    return image, ImageDraw.Draw(image), base_fonts(), palette()


def save_image(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(path, quality=96)


def draw_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    no: str,
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
    draw.text((x1 + 44, y1 + 26), no, font=fonts["tag"], fill=colors["ink"])
    draw.text((x1 + 24, y1 + 84), title, font=fonts["card_title"], fill=colors["white"])
    draw_text_block(
        draw,
        (x1 + 24, y1 + 124),
        subtitle,
        font=fonts["body"],
        fill=colors["muted2"],
        max_width=x2 - x1 - 48,
        line_gap=4,
    )
    current_y = y1 + 196
    for item in items:
        draw.ellipse((x1 + 28, current_y + 8, x1 + 40, current_y + 20), fill=accent)
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
    foot = (x1 + 22, y2 - 104, x2 - 22, y2 - 22)
    rounded(draw, foot, fill=colors["chip"], outline=accent, width=2, radius=18)
    draw.text((x1 + 38, y2 - 92), "图示说明", font=fonts["mini_bold"], fill=colors["white"])


def render_overview() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "自动化交易比赛系统 IPO 分解总图", font=fonts["title"], fill=colors["white"])
    draw.text(
        (88, 148),
        "编号体系：1 输入，2 处理，3 输出。各分解图继续细化为 1-1、1-2、2-1、2-2、3-1、3-2 等。",
        font=fonts["subtitle"],
        fill=colors["muted"],
    )

    draw_card(
        draw,
        (78, 258, 740, 1000),
        no="1",
        title="输入总览",
        subtitle="系统从控制参数、配置文件、股票清单以及原始逐笔/行情数据装载输入。",
        items=[
            "1-1 控制输入：mode、date、input_dir、output_dir、stock_list_file、build_zip。",
            "1-2 配置输入：dev.yaml、label_dict.yaml，控制阈值、模式、标签映射。",
            "1-3 数据输入：逐笔成交.csv、逐笔委托.csv、行情.csv 或 reference_features.csv。",
        ],
        accent=colors["cyan"],
        fonts=fonts,
        colors=colors,
    )
    draw_card(
        draw,
        (868, 258, 1530, 1000),
        no="2",
        title="处理总览",
        subtitle="当前主链路为日终批处理基线系统，按股票-交易日构造样本并完成识别与聚合。",
        items=[
            "2-1 样本装载与 DailySample 构建。",
            "2-2 日级摘要特征提取与公式变换。",
            "2-3 Task1 交易模式识别。",
            "2-4 Task2 资金类型与意图识别。",
            "2-5 市场 PID 聚合与相对市场度量。",
        ],
        accent=colors["blue"],
        fonts=fonts,
        colors=colors,
    )
    draw_card(
        draw,
        (1658, 258, 2320, 1000),
        no="3",
        title="输出总览",
        subtitle="系统最终导出比赛标准文件、市场状态文件、诊断文件，并保证格式一致性。",
        items=[
            "3-1 标准输出：pattern_reco.csv、predict_result.csv。",
            "3-2 市场输出：market_pid_snapshot.csv、market_regime_report.md。",
            "3-3 诊断与交付：batch_diagnostics.json、label_distribution.csv、submit.zip。",
        ],
        accent=colors["amber"],
        fonts=fonts,
        colors=colors,
    )
    draw_arrow(draw, (740, 628), (868, 628), color=colors["line"], width=7)
    draw_arrow(draw, (1530, 628), (1658, 628), color=colors["line"], width=7)
    draw.text(
        (84, 1324),
        "阅读方式：先看总图，再按 1 -> 1-1/1-2/1-3，2 -> 2-1..2-5，3 -> 3-1..3-3 逐层向下分析系统 IPO 过程。",
        font=fonts["footer"],
        fill=colors["muted2"],
    )
    save_image(image, output_dir() / "0-总览_比赛系统IPO分解总图.png")


def render_input_detail() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "1 输入分解图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "把系统输入拆成控制输入、配置输入和数据输入三个层次。", font=fonts["subtitle"], fill=colors["muted"])

    cards = [
        (
            (70, 248, 760, 1140),
            "1-1",
            "控制输入",
            "由 main.py 命令行参数直接控制本次批处理任务的执行边界。",
            [
                "mode：probe 或 batch。",
                "date：指定交易日，决定数据筛选口径。",
                "input_dir / output_dir：定义输入输出目录。",
                "stock_limit / stock_offset：定义抽样切片范围。",
                "stock_list_file：定义指定股票清单。",
                "build_zip：控制是否强制打包 submit.zip。",
            ],
            colors["cyan"],
        ),
        (
            (856, 248, 1546, 1140),
            "1-2",
            "配置输入",
            "由 dev.yaml 与 label_dict.yaml 提供全局运行参数与标签字典。",
            [
                "window_minutes：设计窗口粒度，当前用于系统口径说明。",
                "pattern_low_conf_threshold / pattern_margin_threshold：Task1 回退阈值。",
                "label_mode：资金意图输出压缩模式。",
                "enable_submit_zip / enable_market_snapshot：控制导出链路。",
                "capital_type_labels / capital_intention_labels_submit：提交标签字典。",
            ],
            colors["blue"],
        ),
        (
            (1642, 248, 2332, 1140),
            "1-3",
            "数据输入",
            "系统支持原始逐笔模式和参考特征模式两种装载方案。",
            [
                "原始数据：逐笔成交.csv、逐笔委托.csv、行情.csv。",
                "参考特征：reference_features.csv / features.csv / 参考特征.csv。",
                "目录模式 A：单股票目录直接装载。",
                "目录模式 B：遍历输入目录下的股票子目录。",
                "样本粒度统一为 股票-交易日。",
            ],
            colors["amber"],
        ),
    ]
    for box, no, title, subtitle, items, accent in cards:
        draw_card(draw, box, no=no, title=title, subtitle=subtitle, items=items, accent=accent, fonts=fonts, colors=colors)
    draw_arrow(draw, (760, 694), (856, 694), color=colors["line"], width=7)
    draw_arrow(draw, (1546, 694), (1642, 694), color=colors["line"], width=7)
    draw.text((84, 1320), "输入层关注点：系统先确定边界，再装载配置，最后读取实际业务数据。", font=fonts["footer"], fill=colors["muted2"])
    save_image(image, output_dir() / "1-输入分解图.png")


def render_input_1_1() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "1-1 控制输入图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "说明 main.py 命令行参数如何定义一次批处理任务的执行边界。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="1-1",
        title="命令行控制输入",
        subtitle="控制输入不直接提供业务数据，但决定系统本次运行的目标日期、数据范围、股票范围、输出位置和是否打包。",
        items=[
            "mode：决定是 schema 探针模式 probe，还是批处理模式 batch。",
            "date：指定交易日，是整个样本筛选和输出命名的时间锚点。",
            "input_dir：指定原始数据目录或参考特征目录。",
            "output_dir：指定本次结果输出基目录，系统会自动生成带时间戳的批次目录。",
            "stock_limit / stock_offset：控制样本切片，便于抽样测试、分段处理和性能验证。",
            "stock_list_file：限定本次处理的股票集合。",
            "build_zip：控制是否强制生成 submit.zip。",
        ],
        accent=colors["cyan"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "1-1_控制输入图.png")


def render_input_1_2() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "1-2 配置输入图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "说明配置文件如何决定阈值、标签口径和输出行为。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="1-2",
        title="配置文件输入",
        subtitle="配置文件定义系统以什么规则解释数据、如何回退边界样本、如何导出最终结果。",
        items=[
            "dev.yaml：定义 pattern_low_conf_threshold、pattern_margin_threshold、label_mode、enable_submit_zip 等运行参数。",
            "label_dict.yaml：定义 capital_type_labels、capital_intention_labels_submit、pattern_labels_seed 等标签字典。",
            "配置输入为算法逻辑提供阈值口径，决定低置信样本怎么处理。",
            "配置输入还决定最终输出是细粒度标签还是压缩提交标签。",
            "它不提供事实数据，但提供事实解释规则。",
        ],
        accent=colors["blue"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "1-2_配置输入图.png")


def render_input_1_3() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "1-3 数据输入图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "说明系统的业务数据来源，以及原始逐笔路径与参考特征路径的关系。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="1-3",
        title="业务数据输入",
        subtitle="数据输入是真正驱动模型与规则输出的业务事实来源，所有识别结论最终都要回到这一层校验。",
        items=[
            "原始逐笔路径：逐笔成交.csv、逐笔委托.csv、行情.csv。",
            "参考特征路径：reference_features.csv / features.csv / 参考特征.csv。",
            "目录模式 A：输入目录本身就是单股票目录。",
            "目录模式 B：输入目录下包含多个股票子目录，系统自动遍历。",
            "无论来自哪条路径，系统最终都统一为 股票-交易日 粒度样本。",
        ],
        accent=colors["amber"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "1-3_数据输入图.png")


def render_process_loading() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "2-1 样本装载与构建图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "描述 scheduler.run_daily_batch 如何从目录结构装载样本并构造 DailySample。", font=fonts["subtitle"], fill=colors["muted"])

    cards = [
        (
            (96, 268, 560, 1110),
            "A",
            "输入扫描",
            "先判断输入目录里是否存在 reference_features.csv 等参考特征文件。",
            [
                "若存在，走参考特征路径。",
                "若不存在，判断当前目录是否为单股票目录。",
                "否则遍历目录下全部股票子目录。",
            ],
            colors["cyan"],
        ),
        (
            (680, 268, 1144, 1110),
            "B",
            "数据筛选",
            "按 trade_date 和可选股票清单进行筛选，过滤非目标交易日或不在名单中的股票。",
            [
                "requested_symbols 决定目标股票集合。",
                "stock_limit / stock_offset 决定切片范围。",
                "只保留实际能构造样本的股票。",
            ],
            colors["blue"],
        ),
        (
            (1264, 268, 1728, 1110),
            "C",
            "DailySample 构建",
            "对每个股票-交易日形成一个 DailySample，其中 feature_summary 是后续识别的核心输入。",
            [
                "rows：原始行或参考特征行。",
                "feature_summary：日级摘要特征字典。",
                "quality_flags：标记是否来自参考特征、是否缺失等。",
            ],
            colors["green"],
        ),
        (
            (1848, 268, 2312, 1110),
            "D",
            "兜底逻辑",
            "若指定股票缺失原始数据，则生成默认占位输出，保证最终输出行数完整。",
            [
                "pattern_type 默认：日内套利。",
                "capital_type 默认：散户。",
                "capital_intention 默认：中性。",
                "并写入 warnings 供后续复核。",
            ],
            colors["amber"],
        ),
    ]
    for box, no, title, subtitle, items, accent in cards:
        draw_card(draw, box, no=no, title=title, subtitle=subtitle, items=items, accent=accent, fonts=fonts, colors=colors)
    draw_arrow(draw, (560, 690), (680, 690), color=colors["line"], width=7)
    draw_arrow(draw, (1144, 690), (1264, 690), color=colors["line"], width=7)
    draw_arrow(draw, (1728, 690), (1848, 690), color=colors["line"], width=7)
    save_image(image, output_dir() / "2-1_样本装载与构建图.png")


def render_process_features() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "2-2 日级摘要特征分解图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "说明原始逐笔/行情数据如何变成 Task1、Task2、市场 PID 共用的特征摘要。", font=fonts["subtitle"], fill=colors["muted"])

    cards = [
        (
            (84, 250, 576, 1140),
            "F1",
            "价格方向类",
            "反映价格运动方向、振幅和收盘位置。",
            [
                "close_return = (close_price - prev_close) / prev_close",
                "open_return = (open_price - prev_close) / prev_close",
                "intraday_range = (high_price - low_price) / prev_close",
                "close_strength = (close_price - low_price) / (high_price - low_price)",
            ],
            colors["cyan"],
        ),
        (
            (656, 250, 1148, 1140),
            "F2",
            "成交活跃类",
            "反映成交规模、尾盘活跃度和单笔强度。",
            [
                "deal_amount：总成交额",
                "tail_ratio = tail_trade_amount / total_trade_amount",
                "avg_trade_size = total_trade_amount / trade_count",
                "burst_ratio = max(bucket_amount) / total_bucket_amount",
            ],
            colors["blue"],
        ),
        (
            (1228, 250, 1720, 1140),
            "F3",
            "委托盘口类",
            "反映委托买卖结构、撤单近似比例和盘口支撑/抛压。",
            [
                "order_buy_ratio = buy_orders / (buy_orders + sell_orders)",
                "cancel_ratio：以委托类型非空/非0 近似撤单比",
                "bid_support = bid_vol / (bid_vol + ask_vol)",
                "ask_pressure = ask_vol / (bid_vol + ask_vol)",
            ],
            colors["green"],
        ),
        (
            (1800, 250, 2292, 1140),
            "F4",
            "衍生解释类",
            "反映趋势效率、反转强度与市场家数等辅助特征。",
            [
                "directional_efficiency = min(abs(close_return-open_return)/intraday_range,1)",
                "reversal_strength = close_return - open_return",
                "up_count_market / down_count_market：从行情末条读取",
                "price_impact = abs(close_price - prev_close) / prev_close",
            ],
            colors["amber"],
        ),
    ]
    for box, no, title, subtitle, items, accent in cards:
        draw_card(draw, box, no=no, title=title, subtitle=subtitle, items=items, accent=accent, fonts=fonts, colors=colors)
    draw_arrow(draw, (576, 694), (656, 694), color=colors["line"], width=7)
    draw_arrow(draw, (1148, 694), (1228, 694), color=colors["line"], width=7)
    draw_arrow(draw, (1720, 694), (1800, 694), color=colors["line"], width=7)
    save_image(image, output_dir() / "2-2_日级摘要特征分解图.png")


def render_process_features_2_2_1() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "2-2-1 价格方向特征图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "说明价格方向、振幅和收盘位置类特征如何从行情数据映射出来。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="2-2-1",
        title="价格方向类特征",
        subtitle="这类特征回答的是：今天价格往哪里走、波动有多大、收盘落在全天什么位置。",
        items=[
            "close_return = (close_price - prev_close) / prev_close，用于刻画全天收盘收益方向。",
            "open_return = (open_price - prev_close) / prev_close，用于刻画开盘跳空强弱。",
            "intraday_range = (high_price - low_price) / prev_close，用于刻画日内振幅。",
            "close_strength = (close_price - low_price) / (high_price - low_price)，用于刻画收盘位于全天区间的高低位置。",
            "这些特征共同决定股票是强势收盘、弱势收盘、冲高回落还是低开高走。",
        ],
        accent=colors["cyan"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "2-2-1_price_direction_features.png")


def render_process_features_2_2_2() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "2-2-2 成交活跃特征图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "说明成交规模、尾盘活跃度和爆发强度如何从逐笔成交数据计算出来。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="2-2-2",
        title="成交活跃类特征",
        subtitle="这类特征回答的是：今天交易有多活跃、活跃集中在什么时段、单笔资金强度如何。",
        items=[
            "deal_amount：由逐笔成交价格 × 数量累加得到，反映全天成交规模。",
            "avg_trade_size = total_trade_amount / trade_count，反映平均单笔成交强度。",
            "tail_ratio = tail_trade_amount / total_trade_amount，反映尾盘成交占全日的比重。",
            "burst_ratio = max(bucket_amount) / total_bucket_amount，反映某一时段成交是否集中爆发。",
            "这些特征共同影响游资、量化和尾盘突袭等模式识别结果。",
        ],
        accent=colors["blue"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "2-2-2_trading_activity_features.png")


def render_process_features_2_2_3() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "2-2-3 委托盘口特征图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "说明委托买卖结构、撤单近似比例和盘口支撑/抛压如何构造。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="2-2-3",
        title="委托盘口类特征",
        subtitle="这类特征回答的是：买卖盘力量谁更强、委托节奏是否稳定、盘口是否存在明显抛压。",
        items=[
            "order_buy_ratio = buy_orders / (buy_orders + sell_orders)，反映买向委托占比。",
            "cancel_ratio：当前代码以委托类型字段近似撤单比例，用于刻画扰动和试探行为。",
            "bid_support = bid_vol / (bid_vol + ask_vol)，反映十档买盘支撑强度。",
            "ask_pressure = ask_vol / (bid_vol + ask_vol)，反映十档卖盘抛压强度。",
            "这类特征对资金意图识别、市场 D 值和模式判定都很敏感。",
        ],
        accent=colors["green"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "2-2-3_order_book_features.png")


def render_process_features_2_2_4() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "2-2-4 衍生解释特征图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "说明趋势效率、反转强度、价格冲击和市场家数等衍生解释特征。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="2-2-4",
        title="衍生解释类特征",
        subtitle="这类特征不是直接的价格或成交统计，而是把多个原始量组合成更适合解释行为和市场状态的指标。",
        items=[
            "directional_efficiency = min(abs(close_return - open_return) / intraday_range, 1)，反映趋势推进效率。",
            "reversal_strength = close_return - open_return，反映开盘到收盘的方向反转强度。",
            "price_impact = abs(close_price - prev_close) / prev_close，反映价格冲击幅度。",
            "up_count_market / down_count_market：从行情末条读出，用于横截面广度指标计算。",
            "这类特征主要服务于游资评分、市场 PID 聚合以及相对市场位置解释。",
        ],
        accent=colors["amber"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "2-2-4_derived_explanatory_features.png")


def render_process_task1() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "2-3 Task1 交易模式识别图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "交易模式识别采用 强规则识别 + 候选评分排序 + 低置信回退 的三段式流程。", font=fonts["subtitle"], fill=colors["muted"])

    cards = [
        (
            (120, 288, 670, 1080),
            "T1-A",
            "强规则识别",
            "先抓取非常明显的模式，避免明显样本被评分噪声扰动。",
            [
                "大单吸筹：close_return 高、close_strength 高、deal_amount 大。",
                "尾盘突袭：last15_return 高、tail_ratio 高、close_strength 高。",
                "日内套利：振幅大但收盘偏离不深。",
            ],
            colors["cyan"],
        ),
        (
            (925, 288, 1475, 1080),
            "T1-B",
            "候选评分",
            "对 10 类模式分别计算线性加权得分，取最高者为主候选。",
            [
                "输入分量包括 amount_score、range_score、buy_bias_score、tail_flow_score 等。",
                "例如尾盘突袭 = 0.34*tail_up + 0.22*tail_flow + 0.22*close_top + 0.12*up + 0.10*amount。",
                "本质上是可解释特征到模式标签的显式映射。",
            ],
            colors["blue"],
        ),
        (
            (1730, 288, 2280, 1080),
            "T1-C",
            "低置信回退",
            "若最高分太低，或第一名与第二名差距不足，则退回规则标签。",
            [
                "score < pattern_low_conf_threshold",
                "score - second_score < pattern_margin_threshold",
                "回退逻辑提升稳定性，减少边界样本误判。",
            ],
            colors["amber"],
        ),
    ]
    for box, no, title, subtitle, items, accent in cards:
        draw_card(draw, box, no=no, title=title, subtitle=subtitle, items=items, accent=accent, fonts=fonts, colors=colors)
    draw_arrow(draw, (670, 684), (925, 684), color=colors["line"], width=8)
    draw_arrow(draw, (1475, 684), (1730, 684), color=colors["line"], width=8)
    save_image(image, output_dir() / "2-3_Task1交易模式识别图.png")


def render_process_task1_2_3_1() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "2-3-1 Task1 强规则识别图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "先识别最明显的模式，避免极端样本被后续评分噪声扰动。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="2-3-1",
        title="Task1 强规则识别",
        subtitle="这一步不是对所有模式都打分，而是优先抓住那些特征组合特别明显、业务含义特别直接的样本。",
        items=[
            "大单吸筹：close_return 高、close_strength 高、deal_amount 大，说明全天强势推进且有承接。",
            "连续小单推升：close_return 正、close_strength 高、avg_trade_size 小、order_buy_ratio 偏买。",
            "尾盘突袭：last15_return 高、tail_ratio 高、close_strength 高，说明尾盘集中拉升。",
            "压单吸筹：open_return 偏弱但 close_return 回正，说明盘中承接吸收卖压。",
            "日内套利：abs(close_return) 小但 intraday_range 大，说明高抛低吸特征突出。",
        ],
        accent=colors["cyan"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "2-3-1_task1_rule_detection.png")


def render_process_task1_2_3_2() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "2-3-2 Task1 候选评分图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "对候选模式做显式线性评分，取最高分作为主候选标签。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="2-3-2",
        title="Task1 候选评分",
        subtitle="强规则没有覆盖的样本进入候选评分阶段，本质是把摘要特征归一化后做加权比较。",
        items=[
            "先构造 amount_score、range_score、up_score、buy_bias_score、tail_flow_score 等分量。",
            "对每个候选模式单独定义评分函数，例如尾盘突袭更看重 tail_up_score、tail_flow_score、close_top_score。",
            "模式评分本质是：可解释特征 -> 候选模式相似度。",
            "排序后取最高分标签，并记录第二名分数，为后续低置信回退做准备。",
        ],
        accent=colors["blue"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "2-3-2_task1_candidate_scoring.png")


def render_process_task1_2_3_3() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "2-3-3 Task1 低置信回退图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "对边界样本执行回退机制，提升结果稳定性与可解释性。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="2-3-3",
        title="Task1 低置信回退",
        subtitle="当评分阶段出现不确定性时，系统不强行输出高风险标签，而是退回到更稳健的规则判断。",
        items=[
            "若 score < pattern_low_conf_threshold，则说明最优候选本身不够强。",
            "若 score - second_score < pattern_margin_threshold，则说明第一名和第二名区分度不足。",
            "回退后输出更保守、更稳定的标签，降低边界样本抖动。",
            "这一步是基线规则系统非常关键的稳健性控制装置。",
        ],
        accent=colors["amber"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "2-3-3_task1_fallback.png")


def render_process_task2() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "2-4 Task2 资金识别图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "资金识别先做类型评分，再根据类型分支判断资金意图，最后映射为提交标签。", font=fonts["subtitle"], fill=colors["muted"])

    cards = [
        (
            (84, 268, 620, 1110),
            "T2-A",
            "资金类型评分",
            "同时计算 retail_score、hot_money_score、quant_score。",
            [
                "散户偏好：小单、低成交额、买卖较均衡、趋势效率较低。",
                "游资偏好：大成交额、大单、方向强、尾盘动作明显。",
                "量化偏好：涨跌温和、节奏均衡、爆发度存在、盘口更中性。",
            ],
            colors["cyan"],
        ),
        (
            (700, 268, 1236, 1110),
            "T2-B",
            "类型判定与置信度",
            "取三类分数最大者为 capital_type，并用第一名与第二名分差计算置信度。",
            [
                "capital_type = argmax(retail_score, hot_money_score, quant_score)",
                "capital_confidence = clamp(0.55 + margin/1.5, 0, 1)",
                "若初判散户但涨势特别强，则可上修为游资。",
            ],
            colors["blue"],
        ),
        (
            (1316, 268, 1852, 1110),
            "T2-C",
            "资金意图分支",
            "根据 capital_type 分支判断 买入、卖出、中性、T0交易 或细粒度意图。",
            [
                "游资：拉升、吸筹、出货、试盘。",
                "量化：T0交易、卖出、买入、中性。",
                "散户：T0交易、买入、卖出、中性。",
            ],
            colors["green"],
        ),
        (
            (1932, 268, 2268, 1110),
            "T2-D",
            "提交标签压缩",
            "若 label_mode=compressed，则将细粒度意图压缩为提交所需口径。",
            [
                "吸筹/拉升 -> 买入",
                "出货 -> 卖出",
                "试盘 -> T0交易 或 中性",
                "其他 -> 中性",
            ],
            colors["amber"],
        ),
    ]
    for box, no, title, subtitle, items, accent in cards:
        draw_card(draw, box, no=no, title=title, subtitle=subtitle, items=items, accent=accent, fonts=fonts, colors=colors)
    draw_arrow(draw, (620, 690), (700, 690), color=colors["line"], width=7)
    draw_arrow(draw, (1236, 690), (1316, 690), color=colors["line"], width=7)
    draw_arrow(draw, (1852, 690), (1932, 690), color=colors["line"], width=7)
    save_image(image, output_dir() / "2-4_Task2资金识别图.png")


def render_process_task2_2_4_1() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "2-4-1 Task2 资金类型评分图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "先计算散户、游资、量化三类分数，这是资金识别的第一层。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="2-4-1",
        title="Task2 资金类型评分",
        subtitle="系统不是直接猜标签，而是先分别估计样本更像散户、游资还是量化。",
        items=[
            "retail_score：偏好小单、总成交额较低、买卖更均衡、趋势效率较低。",
            "hot_money_score：偏好大成交额、大单、强方向性、尾盘动作明显、收盘强势。",
            "quant_score：偏好涨跌温和、节奏均衡、存在爆发度但整体更中性。",
            "三类分数使用的是不同的线性组合和业务加分项。",
        ],
        accent=colors["cyan"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "2-4-1_task2_capital_scoring.png")


def render_process_task2_2_4_2() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "2-4-2 Task2 类型判定图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "在三类资金分数之间做比较，选出主标签并计算置信度。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="2-4-2",
        title="Task2 类型判定与置信度",
        subtitle="系统用第一名与第二名的分差作为置信度基础，并在特殊情况下做业务修正。",
        items=[
            "capital_type = argmax(retail_score, hot_money_score, quant_score)。",
            "capital_confidence = clamp(0.55 + margin / 1.5, 0, 1)。",
            "margin 越大，说明最优类别和次优类别差距越明显，置信度越高。",
            "若初判散户但 close_return 和 close_strength 同时很强，则可上修为游资。",
        ],
        accent=colors["blue"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "2-4-2_task2_capital_decision.png")


def render_process_task2_2_4_3() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "2-4-3 Task2 资金意图映射图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "根据资金类型进入分支规则，再压缩为比赛要求的提交标签。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="2-4-3",
        title="Task2 资金意图分支与压缩映射",
        subtitle="资金意图识别分成两层：先给出细粒度行为意图，再决定是否压缩到提交口径。",
        items=[
            "游资分支：拉升、吸筹、出货、试盘、买入、卖出、中性。",
            "量化分支：T0交易、买入、卖出、中性。",
            "散户分支：T0交易、买入、卖出、中性。",
            "若 label_mode=compressed，则细粒度意图再映射为 买入 / 卖出 / 中性 / T0交易。",
        ],
        accent=colors["green"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "2-4-3_task2_intention_mapping.png")


def render_process_market() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "2-5 市场 PID 聚合图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "市场 PID 以单股票特征为底层输入，聚合为市场横截面统计量和市场状态标签。", font=fonts["subtitle"], fill=colors["muted"])

    cards = [
        (
            (110, 288, 640, 1080),
            "M-A",
            "单股 P/I/D",
            "先对每只股票计算 P、I、D 三个值。",
            [
                "P：方向推动强度，包含 net_direction、price_impact、tail_ratio。",
                "I：延续性，包含 burst_ratio、正向 net_direction、tail_ratio。",
                "D：阻尼与扰动，包含 cancel_ratio、ask_pressure-bid_support、弱方向性。",
            ],
            colors["cyan"],
        ),
        (
            (935, 288, 1465, 1080),
            "M-B",
            "横截面聚合",
            "对全部股票做均值、中位数、标准差统计，并计算市场广度。",
            [
                "breadth_ratio = up_count / down_count",
                "breadth_balance = (up_count - down_count) / (up_count + down_count)",
                "P/I/D 统计量进入 market_pid_snapshot.csv。",
            ],
            colors["blue"],
        ),
        (
            (1760, 288, 2290, 1080),
            "M-C",
            "市场状态与相对市场",
            "根据 breadth_balance 与 P/I/D 中位数判定 regime，并生成个股相对市场指标。",
            [
                "强趋势上涨、弱趋势上涨、风险偏好退潮、弱趋势下跌、震荡中性。",
                "p_rel / i_rel / d_rel 进入 PredictResult.debug_info。",
                "trend_score 用于判断强于市场、跟随市场、逆势强股等。",
            ],
            colors["amber"],
        ),
    ]
    for box, no, title, subtitle, items, accent in cards:
        draw_card(draw, box, no=no, title=title, subtitle=subtitle, items=items, accent=accent, fonts=fonts, colors=colors)
    draw_arrow(draw, (640, 684), (935, 684), color=colors["line"], width=8)
    draw_arrow(draw, (1465, 684), (1760, 684), color=colors["line"], width=8)
    save_image(image, output_dir() / "2-5_市场PID聚合图.png")


def render_output_detail() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "3 输出分解图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "输出层拆成比赛标准输出、市场状态输出和诊断交付输出。", font=fonts["subtitle"], fill=colors["muted"])

    cards = [
        (
            (70, 248, 760, 1140),
            "3-1",
            "标准比赛输出",
            "直接服务于比赛提交的标准 CSV 文件。",
            [
                "pattern_reco.csv：stock_code、transaction_date、pattern_type、pattern_explanation。",
                "predict_result.csv：stock_code、transaction_date、capital_type、capital_intention。",
                "两张表最终行数必须一致。",
            ],
            colors["cyan"],
        ),
        (
            (856, 248, 1546, 1140),
            "3-2",
            "市场状态输出",
            "面向市场横截面分析与复核的辅助产物。",
            [
                "market_pid_snapshot.csv：输出 up_count、down_count、breadth、P/I/D 统计量。",
                "market_regime_report.md：输出市场状态文字报告与诊断信息。",
            ],
            colors["blue"],
        ),
        (
            (1642, 248, 2332, 1140),
            "3-3",
            "诊断与交付输出",
            "面向结果复盘、标签分布检查和最终打包交付。",
            [
                "batch_diagnostics.json：批次摘要。",
                "label_distribution.csv：标签频数与占比。",
                "submit.zip：打包 pattern_reco.csv 与 predict_result.csv。",
                "导出前校验表头、字段数、空值、行数一致性。",
            ],
            colors["amber"],
        ),
    ]
    for box, no, title, subtitle, items, accent in cards:
        draw_card(draw, box, no=no, title=title, subtitle=subtitle, items=items, accent=accent, fonts=fonts, colors=colors)
    draw_arrow(draw, (760, 694), (856, 694), color=colors["line"], width=7)
    draw_arrow(draw, (1546, 694), (1642, 694), color=colors["line"], width=7)
    save_image(image, output_dir() / "3-输出分解图.png")


def render_output_3_1() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "3-1 标准比赛输出图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "说明直接服务比赛提交的标准输出文件及其字段口径。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="3-1",
        title="标准比赛输出",
        subtitle="这一层是比赛交付最核心的输出结果，直接对应正式提交文件。",
        items=[
            "pattern_reco.csv：字段为 stock_code、transaction_date、pattern_type、pattern_explanation。",
            "predict_result.csv：字段为 stock_code、transaction_date、capital_type、capital_intention。",
            "两张表的行数必须一致。",
            "导出时要求表头顺序、字段数和空值约束严格通过校验。",
        ],
        accent=colors["cyan"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "3-1_标准比赛输出图.png")


def render_output_3_2() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "3-2 市场状态输出图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "说明面向市场横截面解释的辅助输出文件。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="3-2",
        title="市场状态辅助输出",
        subtitle="这一层不直接用于比赛提交，但用于解释市场所处状态以及个股相对市场的位置。",
        items=[
            "market_pid_snapshot.csv：输出 up_count、down_count、breadth_ratio、breadth_balance、P/I/D 统计量。",
            "market_regime_report.md：输出市场状态说明、PID 摘要和 diagnostics。",
            "它是系统从个股分析走向市场分析的重要辅助产物。",
        ],
        accent=colors["blue"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "3-2_市场状态输出图.png")


def render_output_3_3() -> None:
    image, draw, fonts, colors = make_canvas()
    draw.text((82, 68), "3-3 诊断与交付输出图", font=fonts["title"], fill=colors["white"])
    draw.text((88, 148), "说明用于复盘、自检、标签分布检查和最终打包交付的输出。", font=fonts["subtitle"], fill=colors["muted"])
    draw_card(
        draw,
        (220, 260, 2180, 1140),
        no="3-3",
        title="诊断与交付输出",
        subtitle="这一层确保系统不是只会跑结果，而是具备工程化自检、复盘与交付能力。",
        items=[
            "batch_diagnostics.json：记录样本数、标签分布、市场快照摘要。",
            "label_distribution.csv：记录 pattern_type、capital_type、capital_intention 的分布统计。",
            "submit.zip：打包 pattern_reco.csv 和 predict_result.csv。",
            "导出链路还负责校验提交文件完整性和一致性。",
        ],
        accent=colors["amber"],
        fonts=fonts,
        colors=colors,
    )
    save_image(image, output_dir() / "3-3_诊断与交付输出图.png")


def render_all() -> None:
    render_overview()
    render_input_detail()
    render_input_1_1()
    render_input_1_2()
    render_input_1_3()
    render_process_loading()
    render_process_features()
    render_process_features_2_2_1()
    render_process_features_2_2_2()
    render_process_features_2_2_3()
    render_process_features_2_2_4()
    render_process_task1()
    render_process_task1_2_3_1()
    render_process_task1_2_3_2()
    render_process_task1_2_3_3()
    render_process_task2()
    render_process_task2_2_4_1()
    render_process_task2_2_4_2()
    render_process_task2_2_4_3()
    render_process_market()
    render_output_detail()
    render_output_3_1()
    render_output_3_2()
    render_output_3_3()


def main() -> None:
    parser = argparse.ArgumentParser(description="Render IPO overview and decomposition diagrams")
    parser.parse_args()
    render_all()
    print(f"IPO suite written to: {output_dir()}")


if __name__ == "__main__":
    main()
