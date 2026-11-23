# Habit Tracker: CONTEXT.md

> Documento de contexto **compartido** por los repos de backend y frontend. Se guarda como `docs/CONTEXT.md` en ambos y debe ser **idéntico** en los dos.
> Sirve para (1) pasárselo a una conversación nueva con Claude y (2) recordar decisiones dentro de meses.
> **No incluir secretos** (contraseñas, claves, cadenas de conexión). Los valores de Docker local son solo de desarrollo.

- **Última actualización:** release `v0.3.1` en producción
- **Autor:** Ricardo González
- **Cómo mantenerlo:** actualizarlo en el mismo PR que cierra un pendiente o toma una decisión. Al cerrar un pendiente, se borra de la sección "Pendientes". Si un pendiente afecta a ambos repos, aparece en ambas listas y se borra de las dos al terminar.

---

## 1. Qué es el proyecto

Aplicación full stack de seguimiento de hábitos con gamificación: XP, niveles, rachas, categorías, hábitos diarios, semanales y mensuales, y un historial semanal. Es un **proyecto de aprendizaje** para practicar arquitectura de software y buenas prácticas profesionales.

**Cómo se trabaja (importante para Claude):**

- **Modo mentor.** Explicar el *porqué* de cada decisión (también las de reglas de negocio), señalar el problema y guiar a encontrar la solución, sin regalar todo hecho. Si el usuario se atasca, dar pistas concretas.
- **Cuando se pidan cambios en un archivo, entregar el archivo completo.**
- **Indentación de 2 espacios** en el código nuevo (Python y JS). Dentro de un mismo archivo nunca se mezclan indentaciones (Python falla con `IndentationError`); al editar un archivo antiguo de 4 espacios, respetar el que ya tiene.
- **Tests primero:** escribir el test, ver el rojo, arreglar, ver el verde.
- **Al cerrar una rama o un release, entregar el título y la descripción del PR** (qué hace, cambios, decisiones, cómo probarlo, validación), también para los PR `develop → main`.
- **No asumir, verificar.** Si hay un 500, leer el traceback antes de proponer causas.
- Respuestas en español. Diseño siempre **mobile first**, moderno y profesional.

---

## 2. Arquitectura y despliegue

```
React + Vite (Netlify)  ──REST/JWT──▶  Django REST Framework (Render)  ──▶  PostgreSQL (Supabase)
```

| Pieza | Tecnología | Dónde corre |
|---|---|---|
| Frontend | React 19, Vite 7, Tailwind CSS v4, React Router 7, Axios, react-hot-toast, lucide-react, Vitest | Netlify |
| Backend | Python 3.11, Django 5.2, Django REST Framework, SimpleJWT (5.5.1, con `token_blacklist`), django-cors-headers, WhiteNoise, gunicorn | Render (Docker, `Dockerfile.prod`) |
| Base de datos | PostgreSQL | Supabase (proyectos separados: `habit-tracker` producción y `habit-tracker-dev` desarrollo); Postgres 15 en Docker (tests) |
| CI | GitHub Actions | GitHub |
| Contenedores | Docker Compose (backend, frontend, db) | Local |

**Repos separados:**

- Backend: `Ricardoge25/Habit-Tracker` (carpeta `habit_tracker/` en local; contiene `manage.py`, apps `habit_tracker/` y `habits/`).
- Frontend: `Ricardoge25/HabitTracker-frontend` (carpeta `frontend-habit-tracker/` en local).
- En local ambos viven dentro de una carpeta `habit-tracker-project/` junto al `docker-compose.yml`.

**Despliegue:**

- Render: **Auto-Deploy "On Commit"** desde `main`. El campo *Pre-Deploy Command* está vacío y bloqueado (plan gratuito). **Render NO ejecuta `migrate` solo**: las migraciones se aplican a mano en Supabase **antes** de mergear a `main` (ver sección 3).
- Render, variables de seguridad (sin secretos aquí): `ALLOWED_HOSTS` = el host **exacto** del servicio (`habit-tracker-backend-bj1c.onrender.com`; nunca `.onrender.com`, que acepta cualquier app de la plataforma) y `CORS_ALLOWED_ORIGINS=https://my-habitflow-app.netlify.app` (sin `/` final; un origen mal escrito hace fallar `manage.py check` con `corsheaders.E014`). Producción **no** incluye `localhost`.
- Netlify: despliega desde `main`. Tiene `public/_redirects` con `/* /index.html 200` para que React Router funcione al recargar. Variable `VITE_API_URL` apunta al backend de Render. **`VITE_IDLE_TIMEOUT_MS` NO debe estar definida en Netlify.** No se usan *deploy previews*: usarían el backend de producción con código sin mergear y obligarían a ampliar CORS.
- El backend de desarrollo (Docker local) se conecta al proyecto `habit-tracker-dev` de Supabase.
- Rollback: Netlify → Deploys → publicar el anterior. Render → Events → redeploy del commit anterior (las migraciones aditivas no estorban al código viejo).

---

## 3. Flujo de trabajo con Git

- **Ramas:** `main` = producción; `develop` = integración. Ramas de trabajo cortas con un solo propósito (`fix/...`, `feat/...`, `ci/...`, `chore/...`). El nombre de la rama se revisa antes del primer push (queda para siempre en el merge commit).
- **Ciclo:** rama → PR a `develop` (**Merge commit**) → validar → PR `develop → main` (**Merge commit, nunca squash**) → back-merge `main → develop` → tag.
- **Por qué merge commit entre `develop` y `main`:** con squash las ramas divergen y aparecen conflictos fantasma.
- **Commits:** *Conventional Commits* (`tipo(alcance): descripción`), atómicos y con `git add` explícito (nunca `git add .`, para no colar `.env`). El test y su arreglo van en el mismo commit (ningún commit deja el CI en rojo).
- **Orden de despliegue:** si el release toca ambos repos, **primero backend** (variables de Render → migración manual → merge → Render `Live` → smoke test) y **luego frontend**. El tag se pone en los dos repos cuando ambos están en producción.
- **Release actual:** `v0.3.1` (mismo tag en ambos repos).
- **Migraciones a producción (a mano, antes del merge a `main`):** (1) comprobar con SQL de solo lectura que los datos no violan las restricciones nuevas (o, para tablas nuevas, que aún no existen con `to_regclass`); (2) copia de seguridad si el plan la permite, o un plan de vuelta atrás probado (`migrate <app> <migración anterior>` o `zero` si la app es nueva); (3) desde la consola, con `.env.supabase` (**producción**; `.env` es desarrollo; ninguno se versiona): comprobar que el `ref` del `POSTGRES_USER` coincide con el *Reference ID* de `habit-tracker`, ejecutar `showmigrations <app>` y `migrate <app> --plan`, y solo entonces `migrate <app>` (`<app>` = `habits`, `token_blacklist`...; migrar app por app, nunca `migrate` a secas); (4) verificar el resultado con SQL. El comando carga el archivo con `python-decouple` (en cmd de Windows, comillas dobles): `docker compose exec backend python -c "import os,sys; from decouple import RepositoryEnv; os.environ.update(RepositoryEnv('.env.supabase').data); os.environ.setdefault('DJANGO_SETTINGS_MODULE','habit_tracker.settings'); from django.core.management import execute_from_command_line as run; run(['manage.py']+sys.argv[1:])" <comando de Django>`. Se usa el puerto 5432 (session pooler).
- **Migraciones de librerías** (p. ej. `token_blacklist`): viven en el paquete, no en el repo, así que `makemigrations --check` no las detecta. Por eso la versión de la librería se fija exacta en `requirements.txt`.
- **Protección de ramas:** exigir PR y que pasen los checks (`test` en backend, `lint-and-build` en frontend).

---

## 4. Entorno local (Docker)

`docker-compose.yml` define tres servicios: `backend` (puerto 8000), `frontend` (5173) y `db` (Postgres 15, puerto 5432, con volumen `postgres_data`).

**Regla de oro: todo `python manage.py ...` se ejecuta DENTRO del contenedor `backend`**, no en el Python de Windows (no tiene las dependencias y es 3.10 frente a 3.11 del proyecto).

**Forzar siempre la BD local en tests** (el `.env` del backend apunta a Supabase de desarrollo; un test corrió una vez contra la nube por eso):

```bash
docker compose exec -e POSTGRES_HOST=db -e POSTGRES_PORT=5432 -e POSTGRES_DB=habitdb -e POSTGRES_USER=habituser -e POSTGRES_PASSWORD=habitpass backend python manage.py test habits -v 2 --noinput
docker compose exec -e POSTGRES_HOST=db -e POSTGRES_PORT=5432 -e POSTGRES_DB=habitdb -e POSTGRES_USER=habituser -e POSTGRES_PASSWORD=habitpass backend python manage.py makemigrations --check --dry-run
```

- **Para migrar la BD que usa el servidor de desarrollo (Supabase dev) se ejecuta `migrate` SIN los `-e`**: con ellos solo se migra la base local y `today` responde 500 (`column ... does not exist`). Antes, confirmar con `docker compose exec backend printenv POSTGRES_USER` que el proyecto es el de desarrollo (nunca imprimir contraseñas).
- `.env` de desarrollo del backend: además de la BD, `ALLOWED_HOSTS` (incluye `localhost`) y `CORS_ALLOWED_ORIGINS=http://localhost:5173`. Si cambia el `.env`: `docker compose up -d --force-recreate backend`.
- **Tras `git checkout`, `pull` o `merge` en el backend, reiniciar el contenedor** (`docker compose restart backend`) antes de probar: en Windows el autoreload de Django no siempre detecta los cambios hechos por Git (una ruta nueva respondía 404 con el archivo ya actualizado en disco).
- Si el contenedor `backend` aparece como `not running`, leer `docker compose logs backend --tail 60`: casi siempre es un error al importar `settings.py` (la causa es la **primera** excepción del traceback).
- La BD de pruebas se llama `test_habitdb`. Si aparece `test_postgres`, los tests están apuntando a Supabase: parar.
- La suite completa tarda ~5 min en local (~45 s en CI). Una ejecución que "parece colgada" suele ser lenta: comprobar con `-v 2` qué test corre y con `pg_stat_activity` si hay locks.
- `python manage.py check` detecta en segundos errores de URLs/vistas (un typo `url=` en `@action` tumbó todo el router).
- Frontend: `npm run lint`, `npm test` y `npm run build` (en la carpeta del frontend).
- Logs del backend: `docker compose logs backend --tail 60`.
- Avisos inofensivos: `The "z" variable is not set` viene de un `$` sin escapar en algún `.env`/compose; `No directory at: /app/staticfiles/` es WhiteNoise en desarrollo (no se ejecuta `collectstatic`).
- Si cambia `@theme` o variables `VITE_*`, reiniciar el contenedor del frontend (Vite las lee al arrancar).

---

## 5. Backend: modelo de dominio

Modelos en `habits/models.py`:

- **`CustomUser`** (extiende `AbstractUser`): `email` único y opcional. **Invariante: sin email se guarda `NULL`, nunca `""`** (el `save()` lo fuerza; en Postgres un `UNIQUE` admite varios `NULL` pero un solo `""`). Métodos `current_streak()` y `monthly_completion_rate()`.
- **`Category`**: `user`, `name`, `color` (hex), `unique_together (user, name)`. Al borrarla, los hábitos quedan sin categoría (`SET_NULL`).
- **`Habit`**: `user`, `name`, `description`, `category`, `frequency` (daily/weekly/monthly), `target_per_period`, `unique_together (user, name)`. **`target_per_period` significa repeticiones al día en un diario y días distintos del periodo en un semanal o mensual.** `CheckConstraint`: semanal 1–5, mensual 1–28 (`MAX_WEEKLY_TARGET`, `MAX_MONTHLY_TARGET`), diario sin tope. Métodos `current_streak()`, `week_history()`, `completion_rate()`.
- **`HabitRecord`**: un registro por hábito y día (`date` es `DateTimeField` a medianoche, por eso se filtra con `date__date`), `completed`, `completed_at`, `progress` (contador cuando la meta > 1 en diarios), `note`, y `xp_habit`/`xp_global` (el XP que dio ese registro; sirve para restar exactamente lo mismo al desmarcar).
- **`PeriodBonus`**: bonus ganado al cumplir la meta de un periodo (`habit`, `frequency`, `period_start`, `target`, `xp_habit`, `xp_global`). Único por hábito, frecuencia y periodo.
- **`Progress`**: `user`, `habit` (nullable: `NULL` = progreso **global**), `level`, `experience`. Restricciones únicas **parciales** (migración `0005`): un progreso por (usuario, hábito) y **un solo progreso global por usuario**. Se necesitan porque en SQL `NULL != NULL` y `unique_together` no protege el caso global. `remove_experience` es el inverso exacto de `add_experience` (puede bajar de nivel).
- **Tablas de `token_blacklist`** (de SimpleJWT, no son modelos propios): `OutstandingToken` (cada refresh emitido, se escribe en cada login) y `BlacklistedToken` (los revocados).

La lógica de reglas vive en `habits/services.py` (funciones puras primero, luego las que usan BD). Migraciones de la funcionalidad: `0006` a `0008`, todas aditivas (la `0008` rellena el XP de los registros antiguos con 25/20).

**Reglas de negocio vigentes:**

- **Periodos:** diario = el día; semanal = **lunes a domingo**; mensual = mes calendario. `days_done` = días **distintos** completados en el periodo; el periodo se cumple al llegar a la meta.
- **XP por día:** diario **+20 global, +25 hábito** siempre. En semanales y mensuales **solo dan XP los días hasta alcanzar la meta**; los días extra suman a la racha pero no dan XP.
- **Bonus de periodo:** al alcanzar la meta se da `meta × XP por registro × 50% × (100% + 10% × periodos previos cumplidos, máx. 5)`, una sola vez por periodo. Si se desmarca y el periodo deja de cumplirse, se **revoca**.
- XP para subir de nivel: `nivel × 100`. Al desmarcar se resta exactamente el XP que dio el registro.
- **Racha con tolerancia, por periodos:** un periodo fallado aislado no la rompe; **dos seguidos sí**. El periodo en curso no se penaliza. Se cuenta en **"veces"** (días completados dentro de la racha). `at_risk` lo calcula el backend.
- Solo se modifica el registro **de hoy**; el pasado no se reescribe.
- `TIME_ZONE = America/Bogota`, `USE_TZ = True`.

---

## 6. Backend: API

Base: `/api/`. Autenticación **JWT** (SimpleJWT): access 30 min, refresh 1 día, **sin rotación** (`ROTATE_REFRESH_TOKENS` desactivado a propósito, ver pendientes). Sin credenciales: **401**.

| Endpoint | Métodos | Notas |
|---|---|---|
| `/token/`, `/token/refresh/` | POST | Login y renovación. Un refresh revocado → **401** |
| `/token/blacklist/` | POST | **Logout.** `TokenBlacklistView` de SimpleJWT. Cuerpo `{"refresh": "..."}`. Público (`AllowAny`): poseer el refresh es la prueba, y funciona aunque el access haya caducado. 200 revocado; 401 token inválido o ya revocado; 400 sin `refresh`. Va bajo `token/` para que el interceptor de axios no intente renovar si responde 401 |
| `/register/` | **solo POST** | Público. Valida contraseña en el servidor, normaliza email (`""` → `NULL`, minúsculas, único sin distinguir mayúsculas). No hay list/detalle |
| `/categories/` | CRUD | Filtrado por usuario. Nombre único por usuario sin distinguir mayúsculas |
| `/habits/` | CRUD | Filtrado por usuario. Rechaza nombres duplicados y combinaciones de frecuencia y meta inválidas (400), también en PATCH |
| `/habits/today/` | GET | **Solo lectura**, con número fijo de consultas. Por hábito: `frequency`, `period{start,end}`, `period_target`, `days_done`, `period_met`, `streak_times`, `streak_periods`, `at_risk`, `bonus_earned`, `week_history` (7 días que terminan hoy), `completed_today`, `progress`, `category`... |
| `/habits/{id}/toggle-completion/` | POST | Marca/desmarca hoy; atómico con `select_for_update`; devuelve el XP neto y el `bonus` (`granted`/`revoked`/`none`) |
| `/habits/{id}/update-progress/` | POST | `direction: increment|decrement` para metas > 1. **Solo diarios** (semanal/mensual → 400) |
| `/progress/global/` | GET | Solo lectura. Usuario sin progreso: 200 con nivel 1 / 0 XP **sin escribir** |
| `/progress/{habit_id}/habit-progress/` | GET | Solo lectura. Hábito inexistente o ajeno: **404** (no revela existencia) |
| `/progress/` y `/progress/{id}/` | solo lectura | `POST/PATCH/DELETE` → **405**. `list` devuelve 404 si está vacío (pendiente: debería ser 200 `[]`) |

`/habit-record/` se retiró en `v0.3.0` (el frontend no lo usaba).

**Decisiones de seguridad ya tomadas:**

- Mínimo privilegio: cada viewset expone solo las operaciones de su caso de uso (`RegisterViewSet` = `CreateModelMixin`; `ProgressViewSet` = list + retrieve).
- **El XP lo calcula siempre el servidor.** Los serializers exponen el XP solo en lectura.
- Recursos ajenos devuelven **404, no 403**.
- La restricción de propiedad va **dentro de la consulta** (`get_object_or_404(Habit, pk=pk, user=request.user)`), no en un `if` posterior.
- Los `GET` no deben escribir en la BD.
- Los invariantes de datos se protegen en la capa más baja (modelo/BD), no solo en el serializer.
- No devolver `str(e)` de excepciones internas al cliente.
- **Logout real:** el refresh se revoca en el servidor (blacklist). **Limitación conocida, documentada con un test:** el access ya emitido sigue válido hasta su expiración (30 min), porque los JWT no tienen estado.
- **CORS por entorno:** `CORS_ALLOWED_ORIGINS` desde variable de entorno (producción: solo Netlify; desarrollo: `localhost:5173`); `CORS_ALLOW_ALL_ORIGINS` no se usa. CORS **no es un firewall**: un origen ajeno recibe la misma respuesta, solo que sin `Access-Control-Allow-Origin`, y es el navegador quien bloquea la lectura. Los tests comprueban la cabecera, no el código de estado.
- **`ALLOWED_HOSTS`** con host exacto. Las listas de variables de entorno se leen con `parse_csv_list` (`habit_tracker/env.py`, función pura): `""` → `[]`, sin espacios ni elementos vacíos.

---

## 7. Backend: pruebas y CI

- **170 tests en verde**: `habits/tests.py` (registro, progreso, nombres, XP, frecuencia y `PeriodBonus`) y los archivos `test_services.py` (funciones puras), `test_services_db.py`, `test_record_xp.py`, `test_endpoints_xp.py`, `test_period_status.py`, `test_habit_edit_api.py`, `test_today_api.py`, `test_habit_record_api.py`, `test_env.py` (`parse_csv_list`), `test_cors.py` y `test_token_blacklist.py`.
- **No hay aún tests de CRUD de categorías ni de `monthly_completion_rate`.**
- Patrón de test: Arrange–Act–Assert; verificar la respuesta **y** el estado de la BD (`refresh_from_db()`); crear usuarios con `create_user` y el resto con `create`. La lógica pura se prueba con `SimpleTestCase` (sin BD). En tests de URLs nuevas, usar la URL literal (el rojo es un 404 claro, no un `NoReverseMatch`).
- **Throttle y caché:** el throttle anónimo (10/min) guarda su historial en la **caché**, que no se revierte entre tests como la BD. Todo test que haga peticiones anónimas a endpoints con throttle debe hacer `cache.clear()` en `setUp` **y** `self.addCleanup(cache.clear)`.
- **CI** (`.github/workflows/backend-ci.yml`): Ubuntu + Postgres 15 como servicio con healthcheck; pasos `manage.py check` → `makemigrations --check --dry-run` → `manage.py test habits`. Variables falsas de CI (nunca se toca Supabase). Acciones fijadas a versión mayor; `permissions: contents: read`.
- **Regla:** si cambias un modelo, **incluye la migración en el commit** o el CI falla.

---

## 8. Frontend: estructura y decisiones

```
src/
├── api/axios.js            # Instancia de Axios + interceptores (token y refresh)
├── api/auth.js             # revokeRefreshToken y endSession (logout con blacklist), con auth.test.js
├── context/                # auth-context.js (solo el contexto) y AuthContext.jsx (AuthProvider)
├── hooks/                  # useAuth, useIdleSession, useNow
├── utils/                  # session.js, apiErrors.js, habitUtils.js (con sus *.test.js)
├── components/             # AppHeader, AuthLayout, PasswordInput, Modal, ConfirmDialog,
│                           # HabitList, HabitCard, HabitModal, CategoryList, CategoryModal,
│                           # StatCard, ProgressBar, ProtectRoute, SessionGuard
├── pages/                  # Login, Register, Dashboard, Categories
├── App.jsx                 # Rutas (el AuthProvider vive en main.jsx, una sola vez)
└── index.css               # Tokens de diseño y clases de componente
```

**Rutas:** `/login`, `/register` (públicas); `/home`, `/categories` (protegidas por `ProtectRoute`).

**Reglas de código adoptadas:**

- Un archivo que exporta componentes no exporta también hooks/contexto (compatibilidad con fast refresh): contexto, provider y hook van en archivos separados.
- Funciones de carga con `useCallback` y dependencias correctas en `useEffect`.
- **Estado derivado se calcula, no se guarda** (las estadísticas de "Hoy" salen de `habits` y cuentan solo los hábitos diarios).
- Los updaters de `setState` son puros (sin efectos dentro).
- La fuente de verdad tras crear/editar/marcar es el servidor (`fetchHabits()`).
- **El backend calcula (periodo, racha, riesgo, bonus) y el frontend solo lo muestra.**
- La lógica de presentación va en funciones puras de `habitUtils.js`, con tests.
- Los topes de meta (5 y 28) están duplicados en `FREQUENCY_CONFIG` solo como ayuda; la autoridad es el servidor.
- Las fechas `"YYYY-MM-DD"` se convierten con `parseISODate` (`new Date("YYYY-MM-DD")` interpreta UTC y en Bogotá cae un día antes).
- Los errores de DRF se muestran con `extractApiError`.
- `.sort` siempre sobre una copia.
- Una promesa que se ignora a propósito se marca con `void` (p. ej. `void revokeRefreshToken(refresh)`).

**Sesión y autenticación:**

- Tokens en `localStorage` (`access`, `refresh`, `username`, `lastActivity`). Claves centralizadas en `utils/session.js` (solo constantes y `localStorage`, sin HTTP).
- **Cierre por inactividad a los 5 minutos** (`IDLE_TIMEOUT_MS`, sobrescribible con `VITE_IDLE_TIMEOUT_MS`). Aviso "¿Sigues ahí?" 60 s antes (nunca más de la mitad del timeout). Se compara `Date.now()` con `lastActivity` (no un `setTimeout`, que se pausa al suspender el equipo).
- Sincronización entre pestañas con el evento `storage`; el motivo del cierre (`idle`/`expired`) se muestra en el login. Las demás pestañas no revocan nada: la que cerró sesión ya lo hizo.
- `axios.js`: **un solo refresh compartido** entre peticiones 401 simultáneas (dentro de una pestaña); si falla, dispara el evento `auth:session-expired` y el `AuthContext` cierra sesión **sin recargar la página**.
- **Logout con revocación:** los tres cierres (botón, inactividad y sesión expirada) pasan por `logout` del `AuthContext`, que llama a `endSession()`; el arranque con sesión caducada por inactividad también. `endSession` (1) lee el refresh, (2) lanza `revokeRefreshToken` **sin `await`** y (3) limpia el `localStorage` al instante. `revokeRefreshToken` usa axios "pelado" (no la instancia `api`), timeout de 5 s y **nunca rechaza**. Si la red falla, el cierre no se bloquea y el refresh sigue válido hasta que caduque (máx. 1 día): riesgo aceptado.
- `SessionGuard` se monta dentro de `ProtectRoute`, solo si hay usuario.
- El cierre por inactividad es control de UX; la seguridad la da la revocación del refresh en el servidor (con la limitación del access de 30 min).

**Sistema de diseño (`index.css`):**

- Paleta oscura azul-pizarra, **no negro puro**. Tokens `@theme`: `canvas, surface, surface-2, line, line-strong, ink, ink-muted, ink-faint, accent, accent-hover, accent-soft, success, warning, danger`. Se usan como `bg-surface`, `text-ink-muted`, `border-line`, `bg-accent/15`, etc.
- Clases de componente en **CSS plano** (`.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`, `.field`, `.card`, `.card-glow`). **En Tailwind v4 no se puede hacer `@apply` de una clase propia**; por eso no se usa `@apply` ahí. Los botones llevan siempre `btn btn-primary` (las dos clases).
- **Mobile first:** campos de 16 px (evita el zoom de iOS), objetivos táctiles ≥ 44 px, `min-h-dvh`, modales como **hoja inferior en móvil** y diálogo centrado desde `sm`.
- Tarjetas de hábito por frecuencia: diarios y semanales muestran la **tira L–D de la semana** (letras calculadas desde la fecha real); el stepper +/− existe solo en diarios con meta > 1; los mensuales muestran una barra de progreso. La letra de cada día completado se adapta al color de la categoría (`getContrastTextColor`).
- Dashboard: saludo por hora, fecha y reloj (`useNow`, aislado en un componente pequeño), tres métricas compactas en fila también en móvil, tarjeta de nivel/XP.
- Accesibilidad: etiquetas con `htmlFor`, `aria-*`, foco visible, modales con `Escape`, clic fuera y X.

**CI** (`.github/workflows/frontend-ci.yml`): `npm ci` → `npm run lint` → `npm test` → `npm run build`, con Node 20 y `VITE_API_URL` falso. Lint en **0 errores y 0 warnings**. `eslint.config.js` usa `varsIgnorePattern` y `argsIgnorePattern` con `^[A-Z_]` porque ESLint base no reconoce el JSX como uso.

**Tests:** Vitest 4 (la versión 5 exige Node ≥ 22; el proyecto usa Node 20), entorno `node`, con la zona horaria fijada en `America/Bogota` (`src/test/global-setup.js`). **63 tests** sobre `habitUtils.js`, `apiErrors.js` y `api/auth.js`: no se montan componentes. La red se simula con `vi.mock("axios")` y el `localStorage` con `vi.stubGlobal` (deshecho con `vi.unstubAllGlobals()` en `afterEach`). Los mocks prueban la lógica; la integración real se comprueba a mano en DevTools → Network (incluido el modo *Offline*).

---

## 9. Lecciones aprendidas (no repetir)

1. **`NULL != NULL` en SQL:** rompió el email vacío y el progreso global duplicado. Usar restricciones parciales.
2. **`get_or_create` solo es seguro con restricción única real** en la BD.
3. **Cerrar un agujero no limpia lo que dejó:** revisar y limpiar datos (`email = ''`, filas duplicadas) además de arreglar el código.
4. **Un `except Exception` que devuelve el error interno** es un olor y filtra información.
5. **Tests contra la nube:** siempre forzar las variables de BD local.
6. **`MultipleObjectsReturned`** es un problema de datos, no de lógica: leer el tipo de excepción antes de hipotetizar.
7. **Renombrar un `url_path` rompe los `reverse()` de los tests.** Buscar todos los usos antes.
8. **Hay que probar los caminos felices del frontend** (no solo la seguridad): el cambio de un serializer compartido afectó endpoints que no se tocaron.
9. **Aplicar migraciones aditivas a producción antes del merge**, porque Render no las ejecuta. Vale también para apps de librerías (`token_blacklist`): sin sus tablas, el login daría 500.
10. **Un mismo valor puede significar cosas distintas según la frecuencia** (`target_per_period`): la interfaz decide el control por la frecuencia, no por el número.
11. **Los `-e` de `docker compose exec` solo valen para ese comando:** un `migrate` con ellos no toca la base que usa el servidor.
12. **`.env.supabase` no se puede cargar con `sh`/`source`:** un `)` o un `$` en un valor (p. ej. la contraseña) lo rompe. Leerlo como datos con `python-decouple`.
13. **La caché no se revierte entre tests como la BD.** Los tests de blacklist dejaban peticiones en el throttle y `RegisterEndpointTests` recibía 429 solo en CI: en local la suite tarda ~5 min y la ventana de 60 s caducaba. Si un test pasa en local y falla en CI, sospechar de estado compartido o de dependencia del tiempo.
14. **El autoreload no siempre ve los cambios de Git en Windows:** tras un `checkout`/`pull`, el servidor siguió con el `urls.py` viejo (404 con el archivo correcto en disco). Reiniciar el contenedor antes de probar.
15. **Los mocks no prueban la integración:** los tests del frontend comprobaban la lógica de `revokeRefreshToken`, pero solo la prueba manual en Network detectó que el servidor local respondía 404. Toda función que habla con la red se prueba también a mano.
16. **Las variables de entorno nuevas van a la plataforma antes que el código** (Render): un cambio aislado y verificable que no rompe el código viejo.

---

## 10. Pendientes

> Los pendientes **compartidos** aparecen en las dos listas (marcados con 🔗). Al cerrarlos, se borran de ambas.

### 10.1 Backend

**Seguridad y despliegue**
- 🔗 **Rotación del refresh token** (`ROTATE_REFRESH_TOKENS` + `BLACKLIST_AFTER_ROTATION`): requiere antes coordinar el refresh **entre pestañas** (Web Locks API); si no, dos pestañas renovando a la vez harían que una cerrara sesión. Decidir a la vez si se baja el access de 30 a 10–15 min.
- **Limpieza de `OutstandingToken`:** crece con cada login. Programar `python manage.py flushexpiredtokens` (cron o tarea programada).
- 🔗 **`migrate` automático en el despliegue** (PR de DevOps): p. ej. `CMD ["sh","-c","python manage.py migrate --noinput && gunicorn ..."]` en `Dockerfile.prod`, o Pre-Deploy si el plan lo permite.
- Contenedor de producción corre como **root**; crear usuario sin privilegios.
- Logging estructurado y monitoreo (Sentry).
- Límite de hábitos por usuario.

**Arquitectura y calidad**
- **Dos representaciones del hábito** (el dict armado a mano en `today` y `HabitSerializer`). Unificar en un serializer.
- **Racha duplicada** entre `CustomUser` y `Habit`, y `Habit.mark()` es código muerto (da 10 XP): unificar con `services.py` o eliminar.
- **`HabitRecordAdmin` permite editar XP y registros sin pasar por los servicios:** hacerlo solo lectura o ajustar con una acción que use `set_day_completed`.
- **Historial de eventos de XP** (ledger de eventos) para auditar cambios; hoy el ledger vive en `HabitRecord`.
- `toggle-completion` podría devolver el estado completo del periodo para evitar que el frontend vuelva a pedir `today`.
- **`HabitRecord.date` como `DateTimeField`** a medianoche obliga a `date__date` y produce el warning de datetime naive. Evaluar `DateField` (y zona horaria por usuario).
- `ProgressViewSet.list` devuelve 404 con colección vacía; debería ser 200 con `[]`.
- `habits/apps.py` (`ready()` importa `signals`) y `habits/signals.py` (sobre `User`, no `CustomUser`) son **código muerto**: eliminar.
- Menores: `STATICFILES_STORAGE` obsoleto (usar `STORAGES`), `AUTH_PASSWORD_VALIDATORS` duplicado, `select_related` → `list_select_related` y typo `select_relate` en el admin, mezcla de `config()` y `os.getenv` para la BD, paginación, `$` sin escapar (aviso de la variable `z`).
- **Tests:** aislar la caché del throttle en **toda** la suite (clase base que limpie al empezar y al terminar; `RegisterEndpointTests` hoy depende de que nadie la ensucie antes); medir y acelerar la suite (~5 min en local; evaluar un hasher de contraseñas rápido solo en tests); tests de categorías y `monthly_completion_rate`; organizar los tests en un paquete `habits/tests/`.
- 🔗 **`.editorconfig`** con 2 espacios (`indent_size = 2`, `end_of_line = lf`) en una rama `chore/editorconfig`.

### 10.2 Frontend

**Seguridad y despliegue**
- 🔗 **Rotación del refresh token:** coordinar el refresh entre pestañas (Web Locks API) antes de activarla en el backend.
- 🔗 **Cabeceras de seguridad** con `public/_headers` (`X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` o CSP) y mantener coherencia con el CORS del backend.
- 🔗 **`migrate` automático:** sin cambios en este repo, pero el orden de despliegue (backend antes que frontend) debe respetarse.
- Tokens en `localStorage` (riesgo XSS): evaluar cookie `httpOnly` para el refresh token.

**Arquitectura y calidad**
- **`API_URL` duplicado** en `api/axios.js` y `api/auth.js`: centralizarlo en `src/api/config.js`.
- **TanStack Query** para los datos del servidor: eliminaría fetches manuales, estados de carga y actualizaciones optimistas hechas a mano.
- Extraer un hook `useHabits` de `HabitList` (mezcla UI, HTTP y lógica).
- **Tests de componentes** (Testing Library + `jsdom`): hoy solo se prueban funciones puras.
- **Dockerfiles:** usar `npm ci` en lugar de `npm install --force` (oculta conflictos de dependencias) y producción multi-etapa (build con Node, servir con nginx).
- Subir a Node 22 (y Vitest 5) cuando convenga.
- Acciones de GitHub Actions: `actions/checkout@v4` y `setup-python@v5` avisan por Node 20 deprecado; revisar las versiones mayores vigentes antes de subir. `ubuntu-latest` migra a Ubuntu 26 en octubre de 2026 (el frontend ya fija `ubuntu-24.04`; unificar en el backend).
- Revisar que `HabitCard` y `HabitModal` mantengan accesibilidad con teclado en el menú ⋮.
- 🔗 **`.editorconfig`** con 2 espacios (`indent_size = 2`, `end_of_line = lf`) en una rama `chore/editorconfig`.

### 10.3 Producto e ideas (ambos repos)

> Ideas por definir, sin orden de prioridad. Afectan a los dos repos, por eso viven aquí y no se duplican. Antes de implementar una: definir las reglas de negocio con ejemplos, decidir qué se hace en el backend y qué en el frontend, y abrir su propia rama `feat/...`. Cada pantalla nueva reutiliza `btn`, `field`, `card`, `Modal` y `ConfirmDialog`.

- **Notificaciones o recordatorios** para no olvidar los hábitos. Por decidir el canal (notificaciones push del navegador, correo u otro), quién las programa y a qué hora, y la zona horaria del usuario.
- **Tutorial de uso** de la aplicación para usuarios nuevos (primer inicio de sesión) y accesible después desde la interfaz.
- **Recompensas, metas y logros:** recompensas al llegar a niveles concretos y/o metas o logros que el usuario se pone para conseguir. El XP y los logros los calcula siempre el servidor.
- **Aplicación móvil nativa:** falta investigar opciones y viabilidad antes de decidir (reutilizar la API actual es requisito).
- 🔗 **Refactorizar y organizar la estructura de los dos proyectos** para que sea lo más profesional posible (incluye los pendientes de arquitectura de 10.1 y 10.2, como el paquete `habits/tests/` y el hook `useHabits`).

---

## 11. Cómo usar este documento en una conversación nueva con Claude

1. Pega este archivo completo al empezar el chat.
2. Indica **la rama o tarea** (p. ej. `feat/...`) y sube **solo los archivos que se van a tocar** (`models.py`, `views.py`, `HabitCard.jsx`...).
3. Recuerda el modo de trabajo: mentor, archivos completos, 2 espacios, tests primero, mobile first.
4. Al terminar el trabajo, **actualiza este documento** en el mismo PR (borra los pendientes cerrados, añade decisiones y lecciones) y cópialo idéntico al otro repo.