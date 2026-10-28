#!/usr/bin/env python3
"""1件の利益・売値の下限・仕入れ値の上限を出す（ネットにつながない）

  python3 scripts/rieki.py --sell 4980 --cost 2800
  python3 scripts/rieki.py --sell 4980 --cost 2800 --fee-en 747      # 手数料の実額（SP-API の見積り）がある時
  python3 scripts/rieki.py --sell 4980 --cost-usd 18 --fx 150        # 海外から仕入れる時
  python3 scripts/rieki.py --csv samples/candidates.csv              # まとめて（列 sell, cost, fee_en は任意）
  --json で機械向けに出す

式（円）
  手数料   = 実額（--fee-en）か、売値 × 仮置きの率 ＋ 固定の手数料
  返品の見込み = 売値 × 返品の引当率
  仕入れ   = 仕入れ値 ＋ 仕入れ先からの送料
  利益     = 売値 − 手数料 − 送料 − 梱包 − 返品の見込み − 仕入れ
  ROI      = 利益 ÷ 仕入れ
  出してよい = ROI ≥ 目標 かつ 利益 ≥ 最低利益 かつ 売値が下限〜上限の中

既定の数字は config/settings.json（無ければ settings.example.json）の rieki。
ポイント還元・キャッシュバックは入れない（入れば上振れ）。
"""

import os as _ng_os, sys as _ng_sys  # N-Hack 専用の門（下の3行を消すとこのキットは動きません）
_ng_sys.path.insert(0, _ng_os.path.dirname(_ng_os.path.abspath(__file__)))
import nhack_gate as _nhack_gate  # noqa: E402,F401

import argparse
import csv
import json
import sys

import kit


def keisan(sell, cost, s, fee_en=None):
    r = s["rieki"]
    hr = r["henpin_hikiate_ritsu"]
    if fee_en is not None:
        fee = float(fee_en)
        fr_eff = fee / sell if sell else 0
        fee_src = "実額"
        fixed_fee = 0.0
    else:
        fr_eff = r["fee_rate_karioki"]
        fixed_fee = r["fee_kotei_en"]
        fee = sell * fr_eff + fixed_fee
        fee_src = "仮置き"
    ship = r["souryou_en"] + r["konpou_en"]
    cost_total = cost + r["shiire_souryou_en"]
    henpin = sell * hr
    profit = sell - fee - ship - henpin - cost_total
    roi = profit / cost_total if cost_total > 0 else None

    keep = 1 - fr_eff - hr
    fixed = fixed_fee + ship
    target = max(r["mokuhyo_roi"] * cost_total, r["saitei_rieki_en"])
    floor = (target + fixed + cost_total) / keep if keep > 0 else None
    net = sell * keep - fixed
    max_cost = min(net / (1 + r["mokuhyo_roi"]), net - r["saitei_rieki_en"]) - r["shiire_souryou_en"]

    riyuu = []
    if roi is None or roi < r["mokuhyo_roi"]:
        riyuu.append(f"ROI が目標 {r['mokuhyo_roi'] * 100:.0f}% 未満")
    if profit < r["saitei_rieki_en"]:
        riyuu.append(f"利益が最低 {r['saitei_rieki_en']}円 未満")
    if sell < r["uriage_kagen_en"]:
        riyuu.append(f"売値が下限 {r['uriage_kagen_en']}円 未満")
    if sell > r["uriage_jougen_en"]:
        riyuu.append(f"売値が上限 {r['uriage_jougen_en']}円 超（1回の事故に耐えられるか先に考える）")
    return {
        "sell": sell, "cost": cost, "fee": round(fee), "fee_src": fee_src,
        "ship_konpou": ship, "henpin_mikomi": round(henpin), "profit": round(profit),
        "roi": None if roi is None else round(roi, 4),
        "uriage_kagen_for_mokuhyo": None if floor is None else round(floor + 0.4999),
        "shiire_jougen": round(max_cost - 0.5),
        "dashite_yoi": not riyuu, "riyuu": riyuu,
    }


def show(d):
    print(f"売値 {kit.yen(d['sell'])} ／ 仕入れ {kit.yen(d['cost'])}")
    print(f"  手数料 {kit.yen(d['fee'])}（{d['fee_src']}）・送料と梱包 {kit.yen(d['ship_konpou'])}・返品の見込み {kit.yen(d['henpin_mikomi'])}")
    print(f"  利益 {kit.yen(d['profit'])} ／ ROI {kit.pct(d['roi'])}")
    print(f"  目標を満たす売値の下限 {kit.yen(d['uriage_kagen_for_mokuhyo'])} ／ この売値での仕入れ値の上限 {kit.yen(d['shiire_jougen'])}")
    print("  → 出してよい" if d["dashite_yoi"] else "  → 出さない：" + "／".join(d["riyuu"]))


def main():
    ap = argparse.ArgumentParser(description="1件の利益を出す")
    ap.add_argument("--sell", type=float, help="送料込みの売値（円）")
    ap.add_argument("--cost", type=float, help="仕入れ値（円・割引を引いた後）")
    ap.add_argument("--cost-usd", type=float)
    ap.add_argument("--fx", type=float, help="1ドル何円か（--cost-usd の時に必須・推測で入れない）")
    ap.add_argument("--fee-en", type=float, help="手数料の実額（円）")
    ap.add_argument("--fee-rate", type=float, help="手数料率を上書き")
    ap.add_argument("--ship", type=float, help="送料を上書き")
    ap.add_argument("--csv", help="sell, cost（任意 fee_en）列のある CSV")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    s = kit.settings()
    if a.fee_rate is not None:
        s["rieki"]["fee_rate_karioki"] = a.fee_rate
    if a.ship is not None:
        s["rieki"]["souryou_en"] = a.ship

    rows = []
    if a.csv:
        with open(a.csv, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if not row.get("sell") or not row.get("cost"):
                    continue
                fe = row.get("fee_en") or None
                d = keisan(float(row["sell"]), float(row["cost"]), s, float(fe) if fe else None)
                d["id"] = row.get("id") or row.get("asin") or ""
                rows.append(d)
    else:
        if a.sell is None:
            ap.error("--sell が要ります")
        cost = a.cost
        if a.cost_usd is not None:
            fx = a.fx or s["rieki"].get("kawase_jpy_per_usd")
            if not fx:
                sys.exit("止めます：為替（--fx）がありません。その日の値を確かめて入れてください")
            cost = a.cost_usd * fx
        if cost is None:
            ap.error("--cost か --cost-usd が要ります")
        rows.append(keisan(a.sell, cost, s, a.fee_en))

    if a.json:
        print(json.dumps(rows if a.csv else rows[0], ensure_ascii=False, indent=1))
        return
    for d in rows:
        if d.get("id"):
            print(f"[{d['id']}]")
        show(d)


if __name__ == "__main__":
    main()
