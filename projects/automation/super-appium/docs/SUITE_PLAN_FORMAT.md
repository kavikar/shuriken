# Suite Plan Format

Suite plans live in plans/{brand}.{suite}.json.

Example fields:
- brand: brand3 | Brand One | b2 | Brand Four
- env: qa | enterpriseqa | uat | enterpriseuat | prod | demo
- platform: android | ios
- suite: smoke
- tests[]:
  - key: logical test identifier
  - title: short readable title
  - objective: what this test validates
  - checkpoints[]: required evidence checkpoints

Generated artifacts:
- artifacts/runtime/suites/{brand}.{env}.{platform}.{suite}/combined-suite-prompt.txt
- artifacts/runtime/suites/{brand}.{env}.{platform}.{suite}/suite-manifest.json
- Per-test prompt files in the same suite directory
