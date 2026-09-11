# Menu Domain

Menu engineering automation for Example Corp — data analysis and mapping validation.

## Projects

| Project | Type | Source | Description |
|---------|------|--------|-------------|
| [analyzer](analyzer/) | Flask App | `menu-delta-analyzer` | PROD vs UAT menu comparison — 8 validation checks, Excel reports |
| [mapper](mapper/) | Flask App | `menu-mapping-validator` | Location vs Master menu mapping — POS ID validation, root cause analysis |

## Brands Covered

| Brand | Analyzer | Mapper |
|-------|----------|--------|
| B2 (Brand Two) | Yes | Yes |
| B1 (Brand One) | Yes | Yes |
| B3 (Brand Three) | Yes | Coming soon |

## Source Repositories

These projects live as standalone repos and are registered in Shuriken for unified config/pipeline:
- **analyzer**: `projects/menu/analyzer/`
- **mapper**: `projects/menu/mapper/`
