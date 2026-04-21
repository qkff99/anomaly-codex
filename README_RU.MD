# Anomaly Codex Workbench

English version: [README.md](README.md)

Локальный skill/plugin workbench для Codex под моддинг S.T.A.L.K.E.R. Anomaly 1.5.3.

Этот репозиторий предполагается открывать прямо в Codex или в VS Code. Он содержит:
- локальный STALKER modding skill
- repo-local MCP конфиг для DeepWiki и GitMCP референсов
- helper scripts для создания проектов, импорта, валидации, упаковки, FOMOD, XML encoding и crash-log triage

`AGENTS.md` и `.skills/stalker-modding/SKILL.md` остаются source of truth для агента. Этот README_RU.MD нужен как human quickstart на русском.

## Доступ И Лимиты Codex

- OpenAI блочит граждан РФ, если у вас проблемы с доступом к их сервисам рекомендую вариант обхода блокировок с подменой hosts и специальными DNS - https://dns.geohide.ru:8443/
- Сейчас Codex можно попробовать и из ChatGPT Free / Go, но это обозначено OpenAI как временная доступность. Более широкая включённая доступность есть у Plus, Pro, Business и Enterprise/Edu.
- Не надо считать, что "бесплатно" значит "безлимитно". У Codex есть лимиты по плану, и большие задачи, большие кодовые базы, длинные сессии, cloud-задачи и более тяжёлые reasoning-режимы расходуют доступный лимит заметно быстрее.
- Поэтому в onboarding лучше сразу предупреждать пользователя, что на реальной работе лимиты могут уходить быстро, чтобы это не выглядело как неожиданная "утечка токенов".
- Официальные ссылки:
  - обзор доступа и планов: https://help.openai.com/ru-ru/articles/11369540-using-codex-with-your-chatgpt-plan
  - rate card / credits: https://help.openai.com/ru-ru/articles/20001106-codex-rate-card

## Быстрый Старт

1. Скачай этот репозиторий и распакуй его в обычную рабочую папку на диске.
   Можно использовать ZIP-архив репо или привычный Git workflow. Важно именно открыть в Codex распакованную папку репозитория, а не вложенную подпапку.

2. Установи Codex одним из способов:
   - Codex CLI:
     - официальный getting started: https://help.openai.com/en/articles/11096431-openai-codex-ci-getting-started
     - обзор Codex docs: https://platform.openai.com/docs/codex
   - Codex Desktop app:
     - официальный анонс: https://openai.com/index/introducing-the-codex-app
     - страница продукта: https://openai.com/codex
   - Codex в VS Code:
     - help-статья OpenAI по доступности Codex в VS Code: https://help.openai.com/en/articles/11369540
     - обзор docs/code generation: https://platform.openai.com/docs/guides/code-generation

3. Открой распакованную папку репозитория в Codex или в VS Code с доступным Codex.

4. Зайди в настройки Codex и установи repo-local plugin, если Codex его предложит.
   В этом репо он называется `Anomaly Codex Workspace` / `stalker-modding-workbench`.

5. После установки плагина попроси Codex инициализироваться под этот workspace или спроси, что он теперь умеет.
   Стартовые запросы:
   - `Освойся в этом workspace и скажи, что ты теперь умеешь делать`
   - `Инициализируйся для работы с этим репо`
   - `Какие modding workflows и helper tools доступны в этом workspace?`

6. После этого прогони первые локальные проверки:
   - WSL / Linux:

```bash
./.skills/stalker-modding/scripts/bootstrap_workspace.sh --run-regressions
```

   - PowerShell:

```powershell
.\.skills\stalker-modding\scripts\bootstrap_workspace.ps1 --run-regressions
```

## Первый Запуск

WSL / Linux:

```bash
./.skills/stalker-modding/scripts/bootstrap_workspace.sh
./.skills/stalker-modding/scripts/run_regressions.sh
```

PowerShell:

```powershell
.\.skills\stalker-modding\scripts\bootstrap_workspace.ps1
.\.skills\stalker-modding\scripts\run_regressions.ps1
```

Если нужен быстрый readiness-check плюс полный regression-pass одной командой:

WSL / Linux:

```bash
./.skills/stalker-modding/scripts/bootstrap_workspace.sh --run-regressions
```

PowerShell:

```powershell
.\.skills\stalker-modding\scripts\bootstrap_workspace.ps1 --run-regressions
```

## Workflow Проекта

Создать пустой локальный проект в `projects/<name>`:

```bash
python3 ./.skills/stalker-modding/scripts/init_project.py --name my_mod
python3 ./.skills/stalker-modding/scripts/scaffold_template.py --project my_mod --template lua_feature
python3 ./.skills/stalker-modding/scripts/validate_project.py --project my_mod
python3 ./.skills/stalker-modding/scripts/package_project.py --project my_mod
```

Импортировать копию существующего мода в `projects/`:

```bash
python3 ./.skills/stalker-modding/scripts/import_mod.py --source /path/to/mod-or-gamedata --name imported_mod
```

Вытянуть `configs/` и `scripts/` из всех подпапок MO2 `mods/` в одну общую reference-папку:

```bash
python3 ./.skills/stalker-modding/scripts/extract_mo2_resources.py --source /path/to/ModOrganizer/mods --dest "ai_workspace/user references/mo2-extract"
```

На выходе будут общие `dest/configs` и `dest/scripts`. Конфликты одинаковых путей не затираются молча; по умолчанию первый файл остается, а конфликт попадает в отчет. Для last-wins режима используй `--overwrite`.

Если нужно править существующий мод прямо по месту, а не копировать его в `projects/`, просто дай явный target path и явно скажи, что нужны in-place edits.

## Разбор Логов

Сводка по log file или по целой папке с логами:

```bash
python3 ./.skills/stalker-modding/scripts/log_triage.py summarize /path/to/log/or/logs-dir
```

Для повторяющихся crash-кейсов лучше помнить путь к MO2 `mods/` или к распакованному `gamedata/`, а не к `logs_dir`, потому что эти пути помогают резолвить проблемный аддон обратно в реальные файлы. Внешние пути надо запоминать только с явного разрешения пользователя.

## Packaging И FOMOD

Loose package:

```bash
python3 ./.skills/stalker-modding/scripts/package_project.py --project my_mod
```

Базовый core-only FOMOD package:

```bash
python3 ./.skills/stalker-modding/scripts/fomod_tool.py --project my_mod
```

## Структура Репо

- `projects/` это пользовательская рабочая зона для локальных mod projects
- `tests/fixtures/` содержит repo-tracked regression inputs, а не живые моды
- `ai_workspace/` содержит локальные reference materials
- `.codex-stalker/workspace.json` хранит workspace overlay data и remembered external paths
- `.vscode/mcp.json` зеркалит repo-local plugin MCP configuration

## Заметки

- Используй `ai_workspace/user references` для дополнительных локальных референсов или ссылок на внешние материалы.
- Русские localization XML часто в `windows-1251`; перед правкой legacy XML лучше использовать `xml_localization_tool.py`.
- MO2 тут рассматривается как deployment surface, а не как authoring root. Сначала работай из `projects/`, потом уже упаковывай под MO2, если это нужно.
