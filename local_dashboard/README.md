# Panel local

Desde la raíz del proyecto, ejecuta en PowerShell:

```powershell
py local_dashboard/server.py
```

Abre http://127.0.0.1:8765 y mantén la terminal abierta. Para detenerlo, pulsa Ctrl+C. Si el puerto está ocupado: `py local_dashboard/server.py --port 8766` y abre http://127.0.0.1:8766.

El panel lee `job_scraper/seen_jobs.json`, el perfil y `job_search_tracker.csv`. Permite añadir y editar filas del CSV, que se crea al guardar la primera candidatura. Pulsa «Actualizar datos» después de una búsqueda o cambios externos; también se recarga al volver a la ventana. No ejecuta búsquedas, no sincroniza correo y no actualiza los archivos de fases detalladas `outcome.md`. Para conservar la compatibilidad con el resto del proyecto, no admite comas, comillas ni saltos de línea en los campos editados.

Las ofertas del piloto quedaron solo en `reports/application-dashboard.html` y no se importan automáticamente.

En «Mi perfil», usa «Editar datos» para modificar los valores existentes mediante formularios. Los títulos y la estructura Markdown se conservan. Esta versión permite editar los campos existentes; no añade todavía nuevas filas de formación, idiomas o experiencia. Los cambios se guardan en `01-candidate-profile.md` y no actualizan automáticamente el resumen de `CLAUDE.md`.
