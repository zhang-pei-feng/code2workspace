#!/usr/bin/env bash
# 高风险突变筛选
# 用法: ./risk.sh [ncov|flu|mpxv|all] [threshold=2]
# 示例:
#   ./risk.sh ncov 3        # antibody=3 最高逃逸
#   ./risk.sh flu 2         # anti_risk>=2
#   ./risk.sh all           # 三库均用默认阈值2
set -euo pipefail
DB="${VIRUS_VARIATION_DB:-virus_variation}"
ROOT_PASSWORD="${VIRUS_VARIATION_ROOT_PASSWORD:-zhangpf12345}"

mysql_exec() {
  local sql="$1"
  printf '%s\n' "$ROOT_PASSWORD" | sudo -S -p '' mysql -uroot "$DB" -e "$sql"
}

V="${1:-all}"; T="${2:-2}"

ncov() {
  echo "=== NCOV | antibody>=$T ==="
  mysql_exec "
    SELECT gene, aminoacid_site,
           CONCAT(ref_aminoacid,aminoacid_site,aminoacid) mut,
           ace2, antibody, aminoacid_substitution
    FROM ncov_amino_acid_risk
    WHERE antibody>=$T
    ORDER BY antibody DESC, ace2 DESC, aminoacid_substitution DESC
    LIMIT 50;"
}
flu() {
  echo "=== FLU | anti_risk>=$T ==="
  mysql_exec "
    SELECT reference, gene, ref_aminoacid_site,
           CONCAT(ref_aminoacid,ref_aminoacid_site,aminoacid) mut,
           anti_risk, receptor_risk_26, matrix_risk
    FROM flu_variation
    WHERE anti_risk>=$T
    ORDER BY anti_risk DESC, receptor_risk_26 DESC
    LIMIT 50;"
}
mpxv() {
  echo "=== MPXV | anti_risk>=$T ==="
  mysql_exec "
    SELECT gene, ref_aminoacid_site,
           CONCAT(ref_aminoacid,ref_aminoacid_site,aminoacid) mut,
           anti_risk, matrix_risk
    FROM mpxv_variation
    WHERE anti_risk>=$T
    ORDER BY anti_risk DESC, matrix_risk DESC
    LIMIT 50;"
}

case "$V" in
  ncov) ncov ;;
  flu)  flu  ;;
  mpxv) mpxv ;;
  all)  ncov; echo; flu; echo; mpxv ;;
  *) echo "用法: $0 [ncov|flu|mpxv|all] [threshold]"; exit 1 ;;
esac
