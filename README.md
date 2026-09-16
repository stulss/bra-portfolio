# 홍주형 · 기록으로 이어지는 소개

BR-A 개인 소개 사이트와 기록 갱신 장치. Python 3.11 이상에서 외부 패키지 없이 실행하며, 노션 자동 갱신에는 읽기 권한이 있는 연결 토큰을 환경변수로 사용합니다.

첫 방문자가 약 3분 안에 한 줄 소개, 자기조절력·대인관계력·자기동기력의 변화, 실제 기록, 대표작과 지원 문서를 훑도록 구성했습니다. 이름과 공개 이메일을 표시하며 연락 영역의 버튼은 기본 메일 앱을 엽니다. 상세 기록은 필요할 때만 펼쳐 읽으며 소개 사이트에는 날짜를 표시하지 않습니다.

**공개 사이트: https://hongjuhyung.vercel.app** · **소스: https://github.com/stulss/bra-portfolio**

## 새 폴더에서 실행하는 세 단계
1. 장치 ZIP을 새 폴더에 풀고 그 폴더에서 터미널을 엽니다.
2. `python build.py --input input --output preview`를 실행합니다. `NOTION_TOKEN`이 설정돼 있으면 먼저 노션 DB를 동기화합니다.
3. `preview/index.html`을 브라우저로 열고 이야기·숫자·대표작·문서 링크를 확인합니다. 같은 명령으로 다시 실행하면 같은 파일이 생성됩니다.

## 노션 기록을 자동 갱신하고 승인하기
한 번만 노션 내부 연결을 만들고 `리추얼 기록 DB`를 그 연결에 공유한 뒤, 토큰을 코드가 아닌 Windows 사용자 환경변수에 저장합니다. 새 터미널부터 적용됩니다.

```powershell
[Environment]::SetEnvironmentVariable('NOTION_TOKEN', '노션_내부_연결_토큰', 'User')
```

이후 `python build.py --input input --output preview`만 실행하면 노션의 `날짜`, `구분`, `실천 및 행동`을 먼저 읽어 `input/ritual.json`과 `profile.json`의 내부 기준일을 갱신한 뒤 사이트를 만듭니다. 같은 날짜의 기존 근거 문장은 사람이 고른 내용을 보존하고, 새 날짜에는 실천 문장으로 능력 후보를 만듭니다. 노션 연결 없이 현재 입력만 다시 만들 때는 `--no-sync`를 붙입니다.

직접 보정할 때 `input/ritual.json` 항목은 date(YYYY-MM-DD), sessions(1~2), status(실천했다/일부 실천했다/못 했다/기록 없음), evidence(능력 이름: 실제 기록 문장), source입니다. 날짜당 한 행입니다.
`input/attendance.json`은 date, attended(불리언), source 배열이고 `input/tasks.json`은 id, title, date, submitted(불리언), ability, situation, action, result, source 배열입니다. 원자료가 없으면 빈 배열을 유지합니다. 리추얼을 출석으로 간주하지 않습니다.

실행 후 `preview/candidates.json`에서 날짜·근거가 붙은 후보를 확인합니다. 사이트에 넣으려면 후보 문장을 `input/profile.json`의 story에 옮겨 문장과 근거를 검토하고 approved를 true로 바꿉니다. 후보는 자동 게시되지 않습니다. `--publish`는 본인 작성 문장·스토리 승인·개인정보 점검·앱 예정일을 요구하며, 통과하면 승인된 내용만 출력합니다. 이 옵션 자체는 인터넷에 업로드하지 않습니다.

`python test_build.py`는 재실행 일치·새 폴더 재현·입력 오류·승인 경계를 검사합니다. `python package.py`는 소스·README·공개용 입력·마지막 결과를 포함한 `submission/device.zip`을 생성합니다. 원본 소설·원본 리추얼 전체는 포함하지 않습니다.

## 파일
- `input/`: 공개용으로 선별한 입력. 비밀값·타인의 개인정보를 넣지 마세요.
- `notion_sync.py`: 빌드 전에 노션 리추얼 DB를 읽어 날짜별 공개 입력으로 합칩니다. 연결 토큰은 파일에 저장하지 않습니다.
- `template.html`, `style.css`: 반응형 정적 화면. 데스크톱에서는 소개 축을 고정하고 기록을 오른쪽에서 읽으며, 모바일에서는 한 줄 흐름으로 바뀝니다. 시각 체계는 `docs/01_기획.md` 참고.
  글꼴은 Google Fonts의 Gowun Batang과 IBM Plex Sans KR을 씁니다. 인터넷 없이 열면 `Batang`·`Malgun Gothic` 등으로 대체됩니다. 빌드 자체는 외부 패키지 없이 동작합니다.
- `preview/`: 생성된 사이트·문서 HTML·검토 후보·집계 결과
- `docs/`: 요구사항 매핑, 자료 검증, 배포·검증 안내
- `tmp/hongjuhyung/`: 배포용으로 다시 만든 공개 산출물. 재생성되는 폴더라 원본이 아닙니다.
- `.vercel-project.json`: Vercel 프로젝트 링크 보관본. 지우면 재배포 때 URL이 바뀝니다.
- `작업내역_체크리스트.md`: 진행 기록과 다음 작업

## 지원 문서 PDF
이력서의 직장 경력·학력은 `input/profile.json`의 `employment`·`education`에서 생성합니다. GitHub 원자료와 작성자의 2026-09-16 날짜 정정을 반영했습니다.
`output/pdf/지원문서_홍주형_검토용.pdf`는 현재 HTML을 Playwright로 인쇄한 4쪽 문서입니다. 내용 수정 후에는 documents.html을 다시 인쇄하여 갱신해야 합니다. 기본 갱신 장치와 ZIP은 외부 패키지 없이 HTML 문서를 생성합니다. PDF는 별도 제출 파일이며 자동 갱신 대상이 아닙니다.

## 배포
배포할 때는 검토 후보가 들어 있는 preview 전체가 아니라 `candidates.json`을 뺀 산출물을 올립니다. 배포 명령과 재배포 절차, 그리고 **배포별 URL이 로그인 화면으로 넘어가는 함정**은 `docs/05_배포.md`에 정리돼 있습니다. 제출 URL은 별칭 주소 `https://hongjuhyung.vercel.app` 하나입니다.
