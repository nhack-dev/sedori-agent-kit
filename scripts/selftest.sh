#!/bin/bash
# 道具を全部、ネットにつながず試し運転で1回ずつ動かす。最後に「落ちた道具 0本」と出れば正常
cd "$(dirname "$0")/.." || exit 1
ochi=0
tmp=$(mktemp)
t() {  # 期待する終了コード, 説明, コマンド…
  local want=$1 name=$2; shift 2
  "$@" > "$tmp" 2>&1; local rc=$?
  if [ "$rc" = "$want" ]; then echo "  ok  $name"; else echo "  NG  ${name}（終了コード ${rc}／期待 ${want}）"; sed 's/^/      /' "$tmp" | tail -5; ochi=$((ochi+1)); fi
}
echo "せどりキットの試し運転"
t 0 "利益の計算" python3 scripts/rieki.py --sell 4980 --cost 2300 --fee-en 747
t 0 "利益の計算（まとめて）" python3 scripts/rieki.py --csv samples/candidates.csv --json
t 1 "為替がないと止まる" python3 scripts/rieki.py --sell 4980 --cost-usd 18
t 0 "仕入れ候補の判定" python3 scripts/hantei.py samples/candidates.csv
t 0 "在庫と値段の見直し" python3 scripts/minaoshi.py samples/listings.csv
t 0 "出品文の下書き" python3 scripts/shuppin_bun.py samples/shouhin.json
t 1 "書いてはいけない言葉で止まる" python3 scripts/shuppin_bun.py samples/kensa/ng.json --kensa-dake
t 0 "仕入れ先の検索（試し運転）" python3 scripts/shiire_sagasu.py --jan 4900000000000
t 0 "SP-API 手数料（試し運転）" python3 scripts/sp_api.py fees --asin B0XXXXXXX1 --price 4980
t 0 "SP-API 値段の変更（試し運転）" python3 scripts/sp_api.py nedan --sku SKU-0001 --type PRODUCT --price 4880 --preview
python3 - <<'PY' || ochi=$((ochi+1))
import sys; sys.path.insert(0, "scripts")
import shiire_sagasu as s
assert s.kataban_ok("サンプル HM-000 ホワイト", "HM000")
assert not s.kataban_ok("サンプル HM-0001 ホワイト", "HM-000")
assert s.irisu_of("見本 洗剤 750ml ×3") == 3
assert s.hazusu("【中古】見本", None, None)
assert s.hazusu("【3980円以上で注文可能】見本", None, None)
print("  ok  照合（型番・入り数・中古・最低注文額）")
PY
rm -f "$tmp"
echo "落ちた道具 ${ochi}本"
[ "$ochi" = 0 ]
