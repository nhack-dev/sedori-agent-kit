#!/usr/bin/env python3
"""出品中の商品の在庫と値段を見直し、やることの案を出す（ネットにつながない・案だけ）

  python3 scripts/minaoshi.py samples/listings.csv
  python3 scripts/minaoshi.py samples/listings.csv --json > out/minaoshi.json

入力の列（samples/listings.csv）
  sku, title, sell（今の売値）, cost（今の仕入れ値）, cost_mae（前回見た仕入れ値）, fee_en（手数料の実額・任意）
  shiire_zaiko（仕入れ先の在庫数・分からなければ空）, saiyasu（他の出品者の最安・送料込み）, shiire_2（2つ目の仕入れ先 有/無）

出す案（強い順）
  止める   … 仕入れ先の在庫が少ない／品切れ／今の売値で赤字・目標割れで、下限まで上げても売れる見込みがない
  上げる   … 仕入れ値が上がり、目標を満たす下限が今の売値より上
  合わせる … 最安が下限より上で、少し下げればカートに近づく（下限より下げない）
  そのまま
案をそのまま実行するのは、オーナーが自動にしてよいと決めた範囲だけ（sp_api.py nedan / teishi）。
"""

import os as _ng_os, sys as _ng_sys  # N-Hack 専用の門（下の3行を消すとこのキットは動きません）
_ng_sys.path.insert(0, _ng_os.path.dirname(_ng_os.path.abspath(__file__)))
import nhack_gate as _nhack_gate  # noqa: E402,F401

import argparse
import csv
import json

import kit
import rieki
from hantei import num


def minaosu(row, s):
    m = s["minaoshi"]
    sell, cost = num(row.get("sell")), num(row.get("cost"))
    if sell is None or cost is None:
        return {"an": "要確認", "riyuu": ["売値か仕入れ値が分からない"]}
    r = rieki.keisan(sell, cost, s, num(row.get("fee_en")))
    floor = r["uriage_kagen_for_mokuhyo"]
    zaiko, mae, saiyasu = num(row.get("shiire_zaiko")), num(row.get("cost_mae")), num(row.get("saiyasu"))
    riyuu, an, shin = [], "そのまま", None

    if zaiko is not None and zaiko <= m["shiire_zaiko_min"]:
        an = "止める"
        riyuu.append(f"仕入れ先の在庫 {zaiko:.0f}（{m['shiire_zaiko_min']} 以下）。売れても仕入れられない恐れ")
    elif zaiko is None:
        riyuu.append("仕入れ先の在庫が分からない（今日中に確かめる）")
    if mae and cost > mae * (1 + m["neage_ritsu_alert"]):
        riyuu.append(f"仕入れ値が {mae:,.0f} → {cost:,.0f} 円に上がった")

    if an != "止める" and floor is not None and sell < floor:
        if saiyasu is not None and saiyasu < floor:
            an = "止める"
            riyuu.append(f"今の売値では目標割れ。下限 {floor:,} 円は最安 {saiyasu:,.0f} 円より上で、売れる見込みが薄い")
        else:
            an, shin = "上げる", floor
            riyuu.append(f"目標を満たす下限 {floor:,} 円まで上げる")
    elif an != "止める" and saiyasu is not None and floor is not None and saiyasu < sell:
        target = max(floor, round(saiyasu))
        if target < sell and (sell - target) / sell <= m["kyougou_sa_max"] + 1e-9:
            an, shin = "合わせる", target
            riyuu.append(f"最安 {saiyasu:,.0f} 円に寄せる（下限 {floor:,} 円より下げない）")
        elif target < sell:
            riyuu.append(f"最安 {saiyasu:,.0f} 円との差が大きい。下げ幅が設定を超えるので、オーナーに聞く")
    if (row.get("shiire_2") or "").strip() in ("", "無", "no", "なし"):
        riyuu.append("2つ目の仕入れ先がない（品切れのとき取り消しになる）")
    return {"an": an, "shin_nedan": shin, "riyuu": riyuu, "rieki": r}


def main():
    ap = argparse.ArgumentParser(description="出品中の商品の見直し（案だけ）")
    ap.add_argument("csv")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    s = kit.settings()
    with open(a.csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        o = minaosu(row, s)
        o.update({"sku": row.get("sku", ""), "title": row.get("title", "")})
        out.append(o)
    order = {"止める": 0, "上げる": 1, "合わせる": 2, "要確認": 3, "そのまま": 4}
    out.sort(key=lambda o: order[o["an"]])
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    kazu = {}
    for o in out:
        kazu[o["an"]] = kazu.get(o["an"], 0) + 1
        extra = f" → {o['shin_nedan']:,}円" if o.get("shin_nedan") else ""
        print(f"[{o['an']}{extra}] {o['sku']} {o['title']}")
        for t in o["riyuu"]:
            print(f"    {t}")
    print(f"\n母数 {len(out)} 件 → " + " ／ ".join(f"{k} {v}" for k, v in sorted(kazu.items(), key=lambda kv: order[kv[0]])))


if __name__ == "__main__":
    main()
