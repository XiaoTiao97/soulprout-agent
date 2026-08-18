"""在终端渲染二维码（ASCII）。"""

from __future__ import annotations


def print_terminal_qr(data: str, *, title: str = "请使用手机扫描下方二维码") -> None:
    data = (data or "").strip()
    if not data:
        print("（二维码链接为空，无法展示）")
        return

    print()
    print("=" * 48)
    print(title)
    print("=" * 48)

    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(data)
        qr.print_ascii(invert=True)
    except ImportError:
        print("（未安装 qrcode 库，无法渲染二维码，请安装：pip install qrcode）")
        print(f"扫码链接：{data}")
        return

    print()
    print(f"链接：{data}")
    print("=" * 48)
    print()
