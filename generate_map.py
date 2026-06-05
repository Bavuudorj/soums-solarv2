"""
Статик HTML газрын зураг үүсгэх CLI (Streamlit-гүйгээр).

Ажиллуулах:  python generate_map.py
Үр дүн:      mongolia_electricity_map.html
"""

import sys

from solar import Assumptions
from network import load_soums, load_lines, analyze
from mapbuilder import build_map

# Windows консол дээр кирилл хэвлэхэд гарах алдаанаас сэргийлнэ
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def main(soums_path="soums.xlsx", lines_path="lines.xlsx",
         output_html="mongolia_electricity_map.html"):
    soums = load_soums(soums_path)
    lines = load_lines(lines_path)
    assumptions = Assumptions()
    analysis = analyze(soums, lines, assumptions)
    m = build_map(soums, lines, assumptions, analysis=analysis)
    m.save(output_html)

    s = analysis['summary']
    print(f"Газрын зураг үүслээ: {output_html}")
    print(f"  Сум: {len(soums)} | Шугам: {len(lines)} | Сүлжээ: {s['n_networks']}")
    print(f"  Хамгийн бага нийт зардал: ${s['total_min_cost']:,.0f} "
          f"(хэмнэлт ${s['total_savings']:,.0f})")
    print(f"  Төвлөрсөн: {s['n_centralized']} | Тараангуй: {s['n_distributed']}")


if __name__ == '__main__':
    main()
