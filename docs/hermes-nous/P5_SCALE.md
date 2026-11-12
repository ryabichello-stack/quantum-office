# P5 — Масштаб и биллинг

- Пока MCP discovery process-global — **runtime на tenant**, не multiplex.  
- Перед 100 компаниями: замер idle RSS одного runtime.  
- Meter: event `hermes_nous.run_started` при create_run (bridge).  
- API stub: `GET /v1/hermes-nous/scale-notes`.  
- Evals / prompt-injection — отдельный прогон после P1 dogfood.
