QUANTUM LABS AVA — MAILER ENTRYPOINT PROTECTION
==============================================

NEVER replace /opt/ava-mailer/main.py with:
  - main.py.legacy-stripped-DO-NOT-USE
  - any file named "main copy.py"
  - a copy-paste from /root/ava/src/engine.py or /root/ava/main.py

The production entrypoint is the full FastAPI mailer in main.py (calendar, Telemost, post-call).

If main.py was overwritten by mistake, restore from:
  - /root/backups/quantum-labs-full-*.tar.gz (backup_quantum_labs.sh)
  - or git/deploy artifact for this server

Legacy stripped snapshot (DO NOT RUN as uvicorn entry):
  /opt/ava-mailer/main.py.legacy-stripped-DO-NOT-USE
  See: main.py.legacy-stripped-DO-NOT-USE.README
