# Automation Domain

Mobile app E2E testing and device automation for Example Corp brands.

## Projects

| Project | Type | Description |
|---------|------|-------------|
| [maestro](maestro/) | Maestro E2E | Device-cloud Maestro flows for Brand One, Brand Two, Brand Three, Brand Four |
| [super-appium](super-appium/) | Appium MCP | Brand-aware agentic mobile smoke harness |
| [playwright-web](playwright-web/) | — | Pointer only. Web E2E lives in [play-left](https://github.com/kavikar/play-left) |

Mobile is this domain's scope. Web end-to-end automation was split into its own
repository rather than kept here as a second, thinner Playwright project — see
[playwright-web/README.md](playwright-web/README.md) for the reasoning and the
interface between the two.

## Adding a New Automation Project

1. Create a directory under `projects/automation/<project-name>/`
2. Register it in `config/projects.yaml` under `domains.automation.projects`
3. Run `python scripts/ci/write-gitlab-ci.py` to regenerate the pipeline
