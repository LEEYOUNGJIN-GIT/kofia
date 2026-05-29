# PRD: Kofia 일반펀드 자산배분 수집

| 항목 | 내용 |
|------|------|
| **문서 버전** | 0.4 |
| **작성일** | 2026-05-29 |
| **상태** | Draft — 구현 전 |
| **관련 문서** | [보유 펀드 목록](./holdings_fund_list.md) |

---

## 1. 배경·문제

- 보유 **일반펀드(비상장)** 다수(약 34종)의 **분기 자산배분·상위 보유종목**은 KOFIA 전자공시(dis.kofia)에 있으나, **공식 REST API로 개별 펀드 배분을 일괄 조회할 수 없다**.
- 펀드명·클래스 표기가 제각각이고, **재간접·TDF** 등은 해석이 달라 수동 확인 비용이 크다.
- **일별 자산배분**은 법정 공시 범위를 벗어나며, 본 프로젝트 목표와도 맞지 않는다.

---

## 2. 목표 (Goals)

1. `config/fund_list.yaml`에 정의된 펀드에 대해 **분기마다 자산군 비중**을 구조화해 `data/timeseries/`에 **시계열로 누적**한다.
2. 필요 시 **과거 4~8분기 백필**로 TDF·혼합펀드 등 **배분 추세**를 분석할 수 있게 한다.
3. (2단계) **상위 10종목** 등 보유종목 요약을 동일 시계열 체계로 저장한다.
4. **GitHub Actions만**으로 수집·테스트·CSV 반영까지 운영한다 (일배치 없음, §7.10).
5. 펀드 추가·제외는 **설정 파일·문서만 수정** — 코드 변경 최소화.
6. **Playwright·헤드리스 브라우저 미사용** — `requests` + HTML/PDF 파싱만 (§3, §7.10).

---

## 3. 비목표 (Non-Goals)

| 항목 | 사유 |
|------|------|
| 투자 권고·리밸런싱 신호 | 정보 수집만; 투자 조언 아님 |
| 일별 NAV·일별 자산배분 | 공시 한계·요구 없음 |
| ETF·발행어음 | 별도 상품·데이터 경로 |
| 유료 DB(한국펀드평가 등) | 비용·라이선스 범위 외 |
| 실시간 대시보드 UI | 1차는 CSV·Git 저장 |
| **Playwright / Selenium / 헤드리스 Chrome** | GHA 복잡도·용량·유지보수 — **아키텍처상 금지** (§7.10) |
| 로컬 전용 수집 파이프라인 | GHA와 **동일 CLI**만 허용; 로컬만의 별도 경로 없음 |

---

## 4. 사용자·이해관계

| 역할 | 니즈 |
|------|------|
| **운영자(본인)** | 보유 펀드 포트폴리오·분기 배분 추이 확인, 펀드 리스트 변경 |
| **분석(향후)** | CSV/시계열로 거시지표(ECOS 등)와 분기말 조인 |

---

## 5. 기능 요구사항

### 5.1 Must Have (MVP)

| ID | 요구사항 | 완료 기준 |
|----|----------|-----------|
| F-01 | `fund_list.yaml`에서 `enabled: true` 펀드만 처리 | 비활성 펀드는 수집 스킵 |
| F-02 | dis.kofia 분기 공시에서 **자산군 비중** 추출 | `fund_allocation.csv`에 `bas_dt`·`asset_class`·`weight_pct` 행 저장 |
| F-03 | 시계열 **upsert** (§7.8) | 동일 `(srtn_cd, bas_dt, asset_class)` 재실행 시 **덮어쓰기** + `fetched_at` 갱신, 중복 행 없음 |
| F-04 | `workflow_dispatch`로 분기·백필 실행 | GHA 로그·산출물 확인 가능 |
| F-05 | 34종 `srtn_cd` 확정 및 YAML 반영 | [holdings_fund_list.md](./holdings_fund_list.md)와 YAML 일치 |

### 5.2 Should Have

| ID | 요구사항 | 완료 기준 |
|----|----------|-----------|
| F-10 | 상위 10종목 추출 | `fund_holdings_top10.csv` |
| F-11 | 과거 N분기 백필 CLI/입력 | `--backfill 8` 등 |
| F-12 | (선택) 원본 PDF/HTML `data/archive/` 보관 | 분기·alias별 경로 |
| F-13 | 자산군 `weight_pct` 합계 검증 | 펀드·분기별 합 95~105% — WARNING/ERROR 로그 (§7.8) |
| F-14 | 실행 로그 `data/logs/run_{date}.json` | 성공/실패 펀드·분기 목록, GHA artifact |

### 5.3 Could Have

| ID | 요구사항 |
|----|----------|
| F-20 | `fund_lookup.py` — 표준코드 1회 조회 (공공 API) |
| F-21 | ECOS/KOSIS 분기말 시리즈와 조인 스크립트 |
| F-22 | 34종 **가중 포트폴리오** 집계 (잔액 입력 필요) |

---

## 6. 비기능 요구사항

| ID | 항목 | 기준 |
|----|------|------|
| NF-01 | **갱신 주기** | 분기 1회 (+ 수동 백필) |
| NF-02 | **규정 준수** | dis.kofia 이용약관·robots.txt 준수, 과도한 요청 금지 |
| NF-03 | **비밀** | Private repo, 보유 목록·잔액 미공개 |
| NF-04 | **재현성** | 동일 분기·동일 공시 → 동일 CSV (파서 버전 기록 권장) |
| NF-05 | **유지보수** | 공시 HTML/PDF 변경 시 파서 수정 — 단일 모듈 `dis_parser.py` |
| NF-06 | **요청 제한** | 펀드·문서 요청 간 **1~2초 delay**, 타임아웃 30s, 실패 시 최대 3회 재시도 |
| NF-07 | **테스트** | `tests/fixtures/` 샘플 HTML/PDF 1건 + golden CSV — **GHA `test.yml`** 에서 회귀 |
| NF-08 | **GHA 단일 런타임** | 수집·백필·(선택) API 조회는 **모두** `ubuntu-latest` workflow에서 실행 |
| NF-09 | **HTTP-only 수집** | dis 접근은 `requests` 세션 + POST/GET + PDF 바이너리 다운로드만 |

---

## 7. 데이터·아키텍처

### 7.1 흐름

```
docs/holdings_fund_list.md → fund_list_sync.py → config/fund_list.yaml
                                                      ↓
                                            dis_parser.py → data/timeseries/*.csv
                                                      ↑
                                    GitHub Actions (holdings push / workflow_dispatch)
```

- **일배치 없음** — 분기 공시·수동 백필만.
- **API 필수 아님** — 자산배분은 dis.kofia 공시 파싱. 표준코드 1회 조회 시에만 `DATA_GO_KR_API_KEY` (선택).

### 7.2 데이터 소스

| 우선순위 | 소스 | 용도 |
|----------|------|------|
| 1 | [dis.kofia.or.kr](http://dis.kofia.or.kr) | 분기영업·결산·자산운용보고서 — **자산배분·top10** |
| 2 | (선택) [공공데이터 펀드상품기본정보](https://www.data.go.kr/tcs/dss/selectApiDataDetailView.do?publicDataPk=15094792) | `srtn_cd`·메타 1회 조회 |
| — | DART, fund.kofia | 보조·설정 단계 위주 |

개별 펀드 **자산군 비중 REST API는 없음** (공시 파싱 필수).

### 7.3 디렉터리 구조

```
Kofia/
├── docs/
│   └── holdings_fund_list.md  # 펀드 마스터 (운영자 편집)
├── config/
│   ├── fund_list.yaml         # sync 자동 생성
│   └── asset_class_map.yaml
├── src/
│   ├── fund_list_sync.py
│   ├── dis_parser.py
│   └── resolve_srtn.py        # (선택)
├── tests/
├── data/timeseries/
├── .github/workflows/
│   ├── sync-and-fetch.yml     # holdings 변경 → sync → fetch
│   ├── kofia-fetch.yml        # 코드 변경 → test → fetch
│   ├── verify-dis.yml
│   └── test.yml
└── requirements.txt
```

### 7.4 시계열 스키마 (`data/timeseries/`)

**`fund_allocation.csv`:** `srtn_cd`, `alias`, `bas_dt`, `report_type`, `asset_class`, `weight_pct`, `source_doc`, `fetched_at`

**`fund_holdings_top10.csv`:** `srtn_cd`, `alias`, `bas_dt`, `rank`, `name`, `asset_type`, `weight_pct`, `fetched_at`

**고유 키·upsert (F-03):**

| 파일 | 키 | 재실행 |
|------|-----|--------|
| `fund_allocation.csv` | `srtn_cd` + `bas_dt` + `asset_class` | 동일 키 **덮어쓰기** |
| `fund_holdings_top10.csv` | `srtn_cd` + `bas_dt` + `rank` | 동일 키 **덮어쓰기** |

**`bas_dt` 규칙:** `2025Q1`→`2025-03-31`, `2025Q2`→`2025-06-30`, `2025Q3`→`2025-09-30`, `2025Q4`/`FY`→`2025-12-31`.

**`asset_class`:** 공시 원문 → `config/asset_class_map.yaml`로 canonical 명칭 매핑 (국내주식, 해외주식, 국내채권, 해외채권, 현금·예금, 기타·파생 등).

### 7.5 `fund_list.yaml` (실행 설정)

```yaml
funds:
  - srtn_cd: "K55105XXXXXXXX"
    alias: "TDF2050_Ce"
    fnd_nm: "미래에셋전략배분적격TDF2050혼합자C-e"
    fnd_tp: "혼합"
    enabled: true
    notes: ""
```

### 7.6 GitHub Actions

| 워크플로 | 트리거 | 작업 |
|----------|--------|------|
| `fetch-allocation.yml` | `workflow_dispatch` (기본), 분기 cron (선택) | `dis_parser` → timeseries upsert → **CSV commit** (Private repo) |

| 항목 | 권장 |
|------|------|
| **기본 실행** | 수동 `workflow_dispatch` (공시 지연 대응) |
| **cron (선택)** | `0 6 20 1,4,7,11 *` UTC — 분기 다음 달 20일 전후 |
| **입력** | `quarter=2025Q3`, `backfill_quarters=8`, `alias=` (단일 펀드 PoC) |
| **산출물** | `data/timeseries/*.csv` commit + `data/logs/run_*.json` artifact |
| **Secrets** | dis만 사용 시 없음 |

로컬과 동일 명령: `python -m src.dis_parser --quarter 2025Q3`

### 7.7 구현 전략

| 단계 | 범위 | 산출 |
|------|------|------|
| **Spike (M0.5)** | TDF2050 1종·최신 1분기 | dis URL·보고서 유형·표/HTML/PDF 구조 메모 |
| **MVP (M1)** | 자산군 비중만, HTML 또는 PDF 파서 v1 | `fund_allocation.csv` 1분기 |
| **Scale (M1~M2)** | `fund_list` 전체 + 백필 | 34종 × N분기 |
| **Should (M2)** | top10, archive, F-13 검증 | holdings top10 CSV |
| **Could (M3)** | ECOS 조인, `fund_lookup` | 선택 |

**보고서 우선순위**

1. **분기영업보고서** — 자산구성·보유종목 상세 (1차)
2. **결산보고서** — 연말(`bas_dt` 12-31)
3. **자산운용보고서** — 1·2 실패 시 fallback (요약·top10)

**파서 기술 (Playwright 없음, §7.10)**

1. WebSquare **백엔드 HTTP** — 검색·목록·다운로드 URL을 Spike에서 캡처(브라우저 DevTools → `curl` 재현)
2. **PDF 직링크** — `pdfplumber`로 「자산구성현황」 표 추출
3. **HTML/XML 응답** — `beautifulsoup4` / `lxml` 표 파싱
4. 위로 불가 시 → **해당 펀드·분기 skip** + `failed[]` 기록 (Playwright 도입 **하지 않음**)

### 7.8 운영·실패 정책

| 항목 | 정책 |
|------|------|
| **Upsert** | §7.4 키 기준 덮어쓰기, `fetched_at`·`parser_version`(run manifest) 갱신 |
| **부분 실패** | 펀드 단위 **continue**; 1건 이상 실패 시 exit code **1**, 성공 목록은 CSV 반영 |
| **Run manifest** | `data/logs/run_{YYYYMMDD}.json` — `parser_version`, `quarter`, `ok[]`, `failed[]`, `source_url` |
| **검증 (F-13)** | `sum(weight_pct)` ∉ [95, 105] → WARNING; ∅ 데이터 → ERROR |
| **수동 검증** | 분기당 표본 3종 (주식·채권·재간접 각 1) — dis 원문 대조 |

### 7.9 CLI 스펙 (`dis_parser`)

```bash
# 최신 분기 1개 (enabled 전체)
python -m src.dis_parser --quarter 2025Q3

# 백필
python -m src.dis_parser --from 2024Q1 --to 2025Q3
python -m src.dis_parser --backfill 8

# PoC / 단일 펀드
python -m src.dis_parser --quarter 2025Q3 --alias TDF2050_Ce

# 드라이런 (URL만 수집)
python -m src.dis_parser --quarter 2025Q3 --dry-run
```

### 7.10 GHA 전용 아키텍처 (Playwright 없음)

**목표:** 로컬·CI 동일 코드 경로. 운영은 **100% GitHub Actions** (로컬은 디버그용만).

#### 7.10.1 적합성 판단

| 영역 | GHA 가능 | 근거 |
|------|----------|------|
| 분기·`workflow_dispatch` 수집 | ✅ | 실행 빈도 낮음, PRD §7.6 |
| `pytest` + fixture (NF-07) | ✅ | push/PR 시 `test.yml` |
| CSV upsert + commit | ✅ | `GITHUB_TOKEN`, Private repo |
| 34종 × 8분기 백필 | ✅ (분할 권장) | job 30~90분 — `matrix` 또는 `alias` 단위 workflow 입력 |
| ECOS/KOSIS (선택) | ✅ | REST + Secrets |
| Playwright | ❌ **사용 안 함** | 비목표 |

#### 7.10.2 dis.kofia — Playwright 없이 가능한 이유·주의

**사이트 특성 (Spike 관찰):**

- 진입 페이지는 JS `location.href` → WebSquare `w2xPath=/wq/main/main.xml`
- UI 셸은 **XML/JS를 HTTP로 직접 요청** 가능 — 전형적인 SPA(클라이언트 렌더 전용)와 다름
- 펀드 검색·공시는 **서버 POST/GET + PDF URL** 패턴일 가능성이 큼 → Spike에서 **HTTP 재현**이 핵심

**주의 (GHA·WAF):**

- 일부 IP(클라우드·해외 CDN)에서 **WAF 차단** 사례 있음
- 완화: `User-Agent`·`Referer`·`Accept-Language: ko`·세션 쿠키·NF-06 delay
- **M0.5 Spike는 GHA `workflow_dispatch` `--dry-run`으로 동일 환경에서 검증** (로컬만 성공은 불충분)

**Playwright 없이 불가할 때 대안 (우선순위):**

| 순서 | 대안 | Playwright |
|------|------|------------|
| 1 | 다른 HTTP 엔드포인트·직접 PDF URL 재시도 | 없음 |
| 2 | `data/archive/`에 수동 다운로드 PDF 넣고 **오프라인 파싱** workflow | 없음 |
| 3 | **self-hosted runner** (집/회사 IP) — 동일 `requests` 코드 | 없음 |
| — | Playwright 도입 | **하지 않음** (범위 변경 시 PRD 개정 필요) |

#### 7.10.3 GHA 워크플로 체계 (3개)

| 파일 | 트리거 | 역할 |
|------|--------|------|
| `test.yml` | `push`, `pull_request` | `pytest` + fixture, **네트워크 없음** |
| `fetch-allocation.yml` | `workflow_dispatch`, (선택) cron | `dis_parser` 수집 → upsert |
| `commit-timeseries.yml` | `fetch` 성공 후 또는 동일 job 내 step | `data/timeseries/` commit |

**`fetch-allocation.yml` 입력 (workflow_dispatch):**

| 입력 | 타입 | 설명 |
|------|------|------|
| `quarter` | string | 예: `2025Q3` |
| `backfill_quarters` | number | 0=단일 분기, 8=백필 |
| `alias` | string | 비우면 전체 `enabled`, PoC 시 `TDF2050_Ce` |
| `dry_run` | boolean | URL·manifest만, CSV 미갱신 |

**백필·장시간 job:**

- `timeout-minutes: 90`
- 실패 많으면 `alias`별 **수동 재실행** (34 parallel matrix는 WAF·예의상 비권장)

**HTTP 클라이언트 (고정):**

```text
requests + urllib3
beautifulsoup4 + lxml
pdfplumber
pyyaml
# playwright, selenium, pyppeteer — requirements.txt 에 금지
```

#### 7.10.4 GHA 성공 게이트 (M0.5 → M1)

| # | 게이트 | 통과 조건 |
|---|--------|-----------|
| G1 | GHA `--dry-run` | TDF2050 1종, 보고서 URL ≥1건 수집 |
| G2 | GHA 실제 파싱 | `fund_allocation.csv` 1분기 행 생성 |
| G3 | GHA 재실행 | upsert 동일 키 덮어쓰기, 중복 행 없음 |
| G4 | (선택) 3종 표본 | 주식·채권·재간접 각 1 — GHA에서 성공 |

G1~G2 미통과 시 M1 착수 보류 — Playwright 대신 §7.10.2 대안 1~3 검토.

---

## 8. 마일스톤

| 단계 | 산출물 | PRD 매핑 |
|------|--------|----------|
| **M0** | `fund_list.yaml` + 표준코드 34종 | F-05 |
| **M0.5** | Spike: **GHA** `--dry-run` + HTTP/PDF 경로 확정, §7.10.4 G1~G2 | §7.10 |
| **M1** | `dis_parser` MVP, **GHA** 최신 1분기, G3 통과 | F-01~F-04, F-14 |
| **M2** | 8분기 백필 + top10 + F-13 검증 | F-10, F-11, F-13 |
| **M3** | (선택) archive, ECOS, `fund_lookup` | F-12, F-20, F-21 |

---

## 9. 성공 지표

| 지표 | 목표 |
|------|------|
| 추적 펀드 커버리지 | `enabled` 펀드 ≥ 90% 분기에서 배분 행 존재 |
| 시계열 깊이 | 핵심 펀드(TDF 등) ≥ 4분기 |
| 수동 검증 | 표본 3종 — 공시 원문 vs CSV 오차 허용 범위 내 |
| 운영 부담 | 분기당 1회 워크플로 (+ 펀드 변경 시만 백필) |

---

## 10. 리스크·완화

| 리스크 | 영향 | 완화 |
|--------|------|------|
| dis 사이트·PDF 구조 변경 | 파서 실패 | archive 원본 보관, dis 수동 검증 |
| 클래스·표준코드 오매칭 | 잘못된 펀드 데이터 | dis 검색 + 클래스 확인 (holdings 절차) |
| 재간접 펀드 of 펀드 | top10 해석 어려움 | **자산군 비중** 우선 |
| 공시 지연 | 최신 분기 공백 | cron을 공시 시즌 이후, `workflow_dispatch` |
| **GHA·WAF 차단** | 클라우드 IP에서 dis 403/차단 | §7.10.2 헤더·delay; 실패 시 self-hosted 또는 수동 archive |
| WebSquare API 변경 | 검색·PDF URL 깨짐 | fixture 테스트 + `parser_version` |

---

## 11. 의존성·제약

| 구분 | 내용 |
|------|------|
| **데이터** | [dis.kofia.or.kr](http://dis.kofia.or.kr) (필수) |
| **런타임** | Python 3.11+, GitHub Actions |
| **Python 패키지** | `pyyaml`, `requests`, `beautifulsoup4`, `lxml`, `pdfplumber` — `requirements.txt` 고정 |
| **금지** | `playwright`, `selenium`, `pyppeteer` |
| **선택** | `pandas` (검증·조인) |
| **GHA** | `ubuntu-latest`, Python 3.11, §7.10.3 워크플로 3종 |
| **인력** | 1인 운영 |
| **법적** | 정보 수집 목적; 투자 권고 아님 |

---

## 12. 문서 맵

| 파일 | 역할 |
|------|------|
| `docs/PRD.md` | **본 문서** — 요구사항·아키텍처·구현 참고 |
| `docs/holdings_fund_list.md` | 보유 펀드 **목록·유형·코드 작업표** |
| `docs/holdings_fund_list.md` | **펀드 마스터** (편집 후 sync) |
| `config/fund_list.yaml` | **실행 설정** (`fund_list_sync.py` 출력) |
| `config/asset_class_map.yaml` | (구현 예정) 자산군 정규화 |

---

## 13. 구현 체크리스트

1. [holdings_fund_list.md](./holdings_fund_list.md) → `config/fund_list.yaml` 이관, `srtn_cd` 확정
2. **M0.5 Spike** — TDF2050 1분기, HTML/PDF 구조·§16 Open Questions 해소
3. `config/asset_class_map.yaml` 초안
4. upsert·`bas_dt` 규칙 코드 반영 (§7.4, §7.8)
5. dis.kofia 이용약관·robots.txt 확인 (NF-06 delay)
6. **GHA** `workflow_dispatch` `--dry-run` (§7.10.4 G1) — 로컬만 성공은 불충분
7. (선택) `DATA_GO_KR_API_KEY`, ECOS/KOSIS
8. Private repo, timeseries CSV commit 정책 확정

---

## 14. 참고 링크

| 링크 | 설명 |
|------|------|
| http://dis.kofia.or.kr | 전자공시 (핵심) |
| https://www.kofia.or.kr/index.do | 금융투자협회 |
| https://fund.kofia.or.kr | 펀드정보 허브 |
| https://www.data.go.kr/tcs/dss/selectApiDataDetailView.do?publicDataPk=15094792 | 펀드상품기본정보 API (선택) |
| https://fine.fss.or.kr/main/prc/fu/sub/fu014.jsp?menuNo=900468 | 금감원 펀드 보고서 안내 |

---

## 15. 승인·변경

| 버전 | 날짜 | 변경 |
|------|------|------|
| 0.1 | 2026-05-29 | 초안 |
| 0.2 | 2026-05-29 | 기술 가이드 통합·폐기 |
| 0.3 | 2026-05-29 | §7.7~7.9 구현 전략, upsert·CLI·실패 정책, M0.5, F-13/14, §16 |
| 0.4 | 2026-05-29 | §7.10 GHA 전용·Playwright 금지, WebSquare HTTP 전략, GHA 게이트 Q6/Q7 |

---

## 16. Open Questions

| # | 질문 | 결정 시점 |
|---|------|-----------|
| Q1 | dis 공시가 **PDF 전용**인지 **HTML 표** 병행인지 | M0.5 Spike |
| Q2 | GHA에서 timeseries **항상 commit** vs artifact만 | M1 전 |
| Q3 | `asset_class` **6분류 고정** vs 공시 원문 유지 | M1 파서 v1 |
| Q4 | ~~Playwright 도입 여부~~ | **결정: 사용 안 함** (§7.10) |
| Q5 | 포트폴리오 가중 집계(F-22) 범위 | M3 또는 비목표 유지 |
| Q6 | GHA에서 WAF 통과 여부 | M0.5 GHA `--dry-run` |
| Q7 | self-hosted runner 필요 여부 | Q6 실패 시 |

---

> **면책:** 정보 수집·설계 목적이며 투자 권고가 아님. 공시 원문을 최종 기준으로 한다.
