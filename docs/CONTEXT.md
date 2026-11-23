# Habit Tracker: CONTEXT.md

> Documento de contexto **compartido** por los repos de backend y frontend. Se guarda como `docs/CONTEXT.md` en ambos y debe ser **idéntico** en los dos.
> Sirve para (1) pasárselo a una conversación nueva con Claude y (2) recordar decisiones dentro de meses.
> **No incluir secretos** (contraseñas, claves, cadenas de conexión). Los valores de Docker local son solo de desarrollo.

- **Última actualización:** release `v0.3.0` en producción
- **Autor:** Ricardo González
- **Cómo mantenerlo:** actualizarlo en el mismo PR que cierra un pendiente o toma una decisión. Al cerrar un pendiente, se borra de la sección "Pendientes". Si un pendiente afecta a ambos repos, aparece en ambas listas y se borra de las dos al terminar.

---

## 1. Qué es el proyecto

Aplicación full stack de seguimiento de hábitos con gamificación: XP, niveles, rachas, categorías, hábitos diarios, semanales y mensuales, y un historial semanal. Es un **proyecto de aprendizaje** para practicar arquitectura de software y buenas prácticas profesionales.

**Cómo se trabaja (importante para Claude):**

- **Modo mentor.** Explicar el *porqué* de cada decisión (también las de reglas de negocio), señalar el problema y guiar a encontrar la solución, sin regalar todo hecho. Si el usuario se atasca, dar pistas concretas.
- **Cuando se pidan cambios en un archivo, entregar el archivo completo.**
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
| Backend | Python 3.11, Django 5.2, Django REST Framework, SimpleJWT, WhiteNoise, gunicorn | Render (Docker, `Dockerfile.prod`) |
| Base de datos | PostgreSQL | Supabase (proyectos separados: `habit-tracker` producción y `habit-tracker-dev` desarrollo); Postgres 15 en Docker (tests) |
| CI | GitHub Actions | GitHub |
| Contenedores | Docker Compose (backend, frontend, db) | Local |

**Repos separados:**

- Backend: `Ricardoge25/Habit-Tracker` (carpeta `habit_tracker/` en local; contiene `manage.py`, apps `habit_tracker/` y `habits/`).
- Frontend: `Ricardoge25/HabitTracker-frontend` (carpeta `frontend-habit-tracker/` en local).
- En local ambos viven dentro de una carpeta `habit-tracker-project/` junto al `docker-compose.yml`.

**Despliegue:**

- Render: **Auto-Deploy "On Commit"** desde `main`. El campo *Pre-Deploy Command* está vacío y bloqueado (plan gratuito). **Render NO ejecuta `migrate` solo**: las migraciones se aplican a mano en Supabase **antes** de mergear a `main` (ver "Pendientes").
- Netlify: despliega desde `main`. Tiene `public/_redirects` con `/* /index.html 200` para que React Router funcione al recargar. Variable `VITE_API_URL` apunta al backend de Render. **`VITE_IDLE_TIMEOUT_MS` NO debe estar definida en Netlify.**
- El backend de desarrollo (Docker local) se conecta al proyecto `habit-tracker-dev` de Supabase.
- Rollback: Netlify → Deploys → publicar el anterior. Render → Events → redeploy del commit anterior (las migraciones aditivas no estorban al código viejo).

---

## 3. Flujo de trabajo con Git

- **Ramas:** `main` = producción; `develop` = integración. Ramas de trabajo cortas con un solo propósito (`fix/...`, `feat/...`, `ci/...`, `chore/...`).
- **Ciclo:** rama → PR a `develop` (**Merge commit**) → validar → PR `develop → main` (**Merge commit, nunca squash**) → back-merge `main → develop` → tag.
- **Por qué merge commit entre `develop` y `main`:** con squash las ramas divergen y aparecen conflictos fantasma.
- **Commits:** *Conventional Commits* (`tipo(alcance): descripción`), atómicos y con `git add` explícito (nunca `git add .`, para no colar `.env`).
- **Orden de despliegue:** si el release toca ambos repos, **primero backend** (migración manual → merge → Render `Live` → smoke test) y **luego frontend**.
- **Release actual:** `v0.3.0` (mismo tag en ambos repos).
- **Migraciones a producción (a mano, antes del merge a `main`):** (1) comprobar con SQL de solo lectura que los datos no violan las restricciones nuevas; (2) copia de seguridad si el plan la permite; (3) desde la consola, con `.env.supabase` (**producción**; `.env` es desarrollo; ninguno se versiona): comprobar que el `ref` del `POSTGRES_USER` coincide con el *Reference ID* de `habit-tracker`, ejecutar `showmigrations habits` y `migrate --plan`, y solo entonces `migrate habits`; (4) verificar el resultado con SQL. El comando carga el archivo con `python-decouple` (en cmd de Windows, comillas dobles): `docker compose exec backend python -c "import os,sys; from decouple import RepositoryEnv; os.environ.update(RepositoryEnv('.env.supabase').data); os.environ.setdefault('DJANGO_SETTINGS_MODULE','habit_tracker.settings'); from django.core.management import execute_from_command_line as run; run(['manage.py']+sys.argv[1:])" <comando de Django>`. Se usa el puerto 5432 (session pooler).
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
- La BD de pruebas se llama `test_habitdb`. Si aparece `test_postgres`, los tests están apuntando a Supabase: parar.
- `python manage.py check` detecta en segundos errores de URLs/vistas (un typo `url=` en `@action` tumbó todo el router).
- Frontend: `npm run lint`, `npm test` y `npm run build` (en la carpeta del frontend).
- Logs del backend: `docker compose logs backend --tail 60`.
- Aviso inofensivo: `The "z" variable is not set` viene de un `$` sin escapar en algún `.env`/compose (pendiente menor de revisar).
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

Base: `/api/`. Autenticación **JWT** (SimpleJWT): access 30 min, refresh 1 día. Sin credenciales: **401**.

| Endpoint | Métodos | Notas |
|---|---|---|
| `/token/`, `/token/refresh/` | POST | Login y renovación |
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

---

## 7. Backend: pruebas y CI

- **151 tests en verde**: `habits/tests.py` (registro, progreso, nombres, XP, frecuencia y `PeriodBonus`) y los archivos `test_services.py` (funciones puras), `test_services_db.py`, `test_record_xp.py`, `test_endpoints_xp.py`, `test_period_status.py`, `test_habit_edit_api.py`, `test_today_api.py` y `test_habit_record_api.py`.
- **No hay aún tests de CRUD de categorías ni de `monthly_completion_rate`.**
- Patrón de test: Arrange–Act–Assert; verificar la respuesta **y** el estado de la BD (`refresh_from_db()`); crear usuarios con `create_user` y el resto con `create`. La lógica pura se prueba con `SimpleTestCase` (sin BD).
- **CI** (`.github/workflows/backend-ci.yml`): Ubuntu + Postgres 15 como servicio con healthcheck; pasos `manage.py check` → `makemigrations --check --dry-run` → `manage.py test habits`. Variables falsas de CI (nunca se toca Supabase). Acciones fijadas a versión mayor; `permissions: contents: read`.
- **Regla:** si cambias un modelo, **incluye la migración en el commit** o el CI falla.

---

## 8. Frontend: estructura y decisiones

```
src/
├── api/axios.js            # Instancia de Axios + interceptores (token y refresh)
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

**Sesión y autenticación:**

- Tokens en `localStorage` (`access`, `refresh`, `username`, `lastActivity`). Claves centralizadas en `utils/session.js`.
- **Cierre por inactividad a los 5 minutos** (`IDLE_TIMEOUT_MS`, sobrescribible con `VITE_IDLE_TIMEOUT_MS`). Aviso "¿Sigues ahí?" 60 s antes (nunca más de la mitad del timeout). Se compara `Date.now()` con `lastActivity` (no un `setTimeout`, que se pausa al suspender el equipo).
- Sincronización entre pestañas con el evento `storage`; el motivo del cierre (`idle`/`expired`) se muestra en el login.
- `axios.js`: **un solo refresh compartido** entre peticiones 401 simultáneas; si falla, dispara el evento `auth:session-expired` y el `AuthContext` cierra sesión **sin recargar la página**.
- `SessionGuard` se monta dentro de `ProtectRoute`, solo si hay usuario.
- El cierre por inactividad es **control de UX, no de seguridad**: el refresh token sigue válido en el servidor (ver pendiente de blacklist).

**Sistema de diseño (`index.css`):**

- Paleta oscura azul-pizarra, **no negro puro**. Tokens `@theme`: `canvas, surface, surface-2, line, line-strong, ink, ink-muted, ink-faint, accent, accent-hover, accent-soft, success, warning, danger`. Se usan como `bg-surface`, `text-ink-muted`, `border-line`, `bg-accent/15`, etc.
- Clases de componente en **CSS plano** (`.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`, `.field`, `.card`, `.card-glow`). **En Tailwind v4 no se puede hacer `@apply` de una clase propia**; por eso no se usa `@apply` ahí. Los botones llevan siempre `btn btn-primary` (las dos clases).
- **Mobile first:** campos de 16 px (evita el zoom de iOS), objetivos táctiles ≥ 44 px, `min-h-dvh`, modales como **hoja inferior en móvil** y diálogo centrado desde `sm`.
- Tarjetas de hábito por frecuencia: diarios y semanales muestran la **tira L–D de la semana** (letras calculadas desde la fecha real); el stepper +/− existe solo en diarios con meta > 1; los mensuales muestran una barra de progreso. La letra de cada día completado se adapta al color de la categoría (`getContrastTextColor`).
- Dashboard: saludo por hora, fecha y reloj (`useNow`, aislado en un componente pequeño), tres métricas compactas en fila también en móvil, tarjeta de nivel/XP.
- Accesibilidad: etiquetas con `htmlFor`, `aria-*`, foco visible, modales con `Escape`, clic fuera y X.

**CI** (`.github/workflows/frontend-ci.yml`): `npm ci` → `npm run lint` → `npm test` → `npm run build`, con Node 20 y `VITE_API_URL` falso. Lint en **0 errores y 0 warnings**. `eslint.config.js` usa `varsIgnorePattern` y `argsIgnorePattern` con `^[A-Z_]` porque ESLint base no reconoce el JSX como uso.

**Tests:** Vitest 4 (la versión 5 exige Node ≥ 22; el proyecto usa Node 20), entorno `node`, con la zona horaria fijada en `America/Bogota` (`src/test/global-setup.js`). **54 tests** sobre `habitUtils.js` y `apiErrors.js`: solo funciones puras, no se montan componentes.

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
9. **Aplicar migraciones aditivas a producción antes del merge**, porque Render no las ejecuta.
10. **Un mismo valor puede significar cosas distintas según la frecuencia** (`target_per_period`): la interfaz decide el control por la frecuencia, no por el número.
11. **Los `-e` de `docker compose exec` solo valen para ese comando:** un `migrate` con ellos no toca la base que usa el servidor.
12. **`.env.supabase` no se puede cargar con `sh`/`source`:** un `)` o un `$` en un valor (p. ej. la contraseña) lo rompe. Leerlo como datos con `python-decouple`.

---

## 10. Pendientes

> Los pendientes **compartidos** aparecen en las dos listas (marcados con 🔗). Al cerrarlos, se borran de ambas.

### 10.1 Backend

**Seguridad y despliegue**
- 🔗 **Blacklist del refresh token** en el logout (`rest_framework_simplejwt.token_blacklist`): hoy el logout solo borra `localStorage` y el refresh sigue válido hasta 1 día.
- 🔗 **`migrate` automático en el despliegue** (PR de DevOps): p. ej. `CMD ["sh","-c","python manage.py migrate --noinput && gunicorn ..."]` en `Dockerfile.prod`, o Pre-Deploy si el plan lo permite.
- 🔗 **CORS:** `CORS_ALLOW_ALL_ORIGINS = True`; restringir al dominio de Netlify y a localhost.
- `ALLOWED_HOSTS` con `.split(",")` sobre `""` da `['']`; limpiar.
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
- Menores: `STATICFILES_STORAGE` obsoleto (usar `STORAGES`), `AUTH_PASSWORD_VALIDATORS` duplicado, `select_related` → `list_select_related` y typo `select_relate` en el admin, mezcla de `config()` y `os.getenv` para la BD, paginación.
- **Más tests:** categorías y `monthly_completion_rate`. Organizar los tests en un paquete `habits/tests/`.

### 10.2 Frontend

**Seguridad y despliegue**
- 🔗 **Blacklist del refresh token:** en el logout, llamar al endpoint del backend antes de limpiar el `localStorage`.
- 🔗 **Cabeceras de seguridad** con `public/_headers` (`X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` o CSP) y mantener coherencia con el CORS del backend.
- 🔗 **`migrate` automático:** sin cambios en este repo, pero el orden de despliegue (backend antes que frontend) debe respetarse.
- Tokens en `localStorage` (riesgo XSS): evaluar cookie `httpOnly` para el refresh token.

**Arquitectura y calidad**
- **TanStack Query** para los datos del servidor: eliminaría fetches manuales, estados de carga y actualizaciones optimistas hechas a mano.
- Extraer un hook `useHabits` de `HabitList` (mezcla UI, HTTP y lógica).
- **Tests de componentes** (Testing Library + `jsdom`): hoy solo se prueban funciones puras.
- **Dockerfiles:** usar `npm ci` en lugar de `npm install --force` (oculta conflictos de dependencias) y producción multi-etapa (build con Node, servir con nginx).
- Subir a Node 22 (y Vitest 5) cuando convenga.
- Acciones de GitHub Actions: `actions/checkout@v4` y `setup-python@v5` avisan por Node 20 deprecado; revisar las versiones mayores vigentes antes de subir. `ubuntu-latest` migra a Ubuntu 26 en octubre de 2026 (el frontend ya fija `ubuntu-24.04`; unificar en el backend).
- Revisar que `HabitCard` y `HabitModal` mantengan accesibilidad con teclado en el menú ⋮.

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
3. Recuerda el modo de trabajo: mentor, archivos completos, tests primero, mobile first.
4. Al terminar el trabajo, **actualiza este documento** en el mismo PR (borra los pendientes cerrados, añade decisiones y lecciones) y cópialo idéntico al otro repo.