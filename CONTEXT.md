# Habit Tracker: CONTEXT.md

> Documento de contexto **compartido** por los repos de backend y frontend. Se guarda como `docs/CONTEXT.md` en ambos y debe ser **idéntico** en los dos.
> Sirve para (1) pasárselo a una conversación nueva con Claude y (2) recordar decisiones dentro de meses.
> **No incluir secretos** (contraseñas, claves, cadenas de conexión). Los valores de Docker local son solo de desarrollo.

- **Última actualización:** release `v0.2.0` en producción
- **Autor:** Ricardo González
- **Cómo mantenerlo:** actualizarlo en el mismo PR que cierra un pendiente o toma una decisión. Al cerrar un pendiente, se borra de la sección "Pendientes". Si un pendiente afecta a ambos repos, aparece en ambas listas y se borra de las dos al terminar.

---

## 1. Qué es el proyecto

Aplicación full stack de seguimiento de hábitos con gamificación: XP, niveles, rachas, categorías y un historial de 7 días. Es un **proyecto de aprendizaje** para practicar arquitectura de software y buenas prácticas profesionales.

**Cómo se trabaja (importante para Claude):**

- **Modo mentor.** Explicar el *porqué* de cada decisión, señalar el problema y guiar a encontrar la solución, sin regalar todo hecho. Si el usuario se atasca, dar pistas concretas.
- **Cuando se pidan cambios en un archivo, entregar el archivo completo.**
- **Tests primero:** escribir el test, ver el rojo, arreglar, ver el verde.
- **No asumir, verificar.** Si hay un 500, leer el traceback antes de proponer causas.
- Respuestas en español. Diseño siempre **mobile first**, moderno y profesional.

---

## 2. Arquitectura y despliegue

```
React + Vite (Netlify)  ──REST/JWT──▶  Django REST Framework (Render)  ──▶  PostgreSQL (Supabase)
```

| Pieza | Tecnología | Dónde corre |
|---|---|---|
| Frontend | React 19, Vite 7, Tailwind CSS v4, React Router 7, Axios, react-hot-toast, lucide-react | Netlify |
| Backend | Python 3.11, Django 5.2, Django REST Framework, SimpleJWT, WhiteNoise, gunicorn | Render (Docker, `Dockerfile.prod`) |
| Base de datos | PostgreSQL | Supabase (producción); Postgres 15 en Docker (desarrollo) |
| CI | GitHub Actions | GitHub |
| Contenedores | Docker Compose (backend, frontend, db) | Local |

**Repos separados:**

- Backend: `Ricardoge25/Habit-Tracker` (carpeta `habit_tracker/` en local; contiene `manage.py`, apps `habit_tracker/` y `habits/`).
- Frontend: `Ricardoge25/HabitTracker-frontend` (carpeta `frontend-habit-tracker/` en local).
- En local ambos viven dentro de una carpeta `habit-tracker-project/` junto al `docker-compose.yml`.

**Despliegue:**

- Render: **Auto-Deploy "On Commit"** desde `main`. El campo *Pre-Deploy Command* está vacío y bloqueado (plan gratuito). **Render NO ejecuta `migrate` solo**: las migraciones se aplican a mano en Supabase **antes** de mergear a `main` (ver "Pendientes").
- Netlify: despliega desde `main`. Tiene `public/_redirects` con `/* /index.html 200` para que React Router funcione al recargar. Variable `VITE_API_URL` apunta al backend de Render. **`VITE_IDLE_TIMEOUT_MS` NO debe estar definida en Netlify.**
- Rollback: Netlify → Deploys → publicar el anterior. Render → Events → redeploy del commit anterior (las migraciones aditivas no estorban al código viejo).

---

## 3. Flujo de trabajo con Git

- **Ramas:** `main` = producción; `develop` = integración. Ramas de trabajo cortas con un solo propósito (`fix/...`, `feat/...`, `ci/...`, `chore/...`).
- **Ciclo:** rama → PR a `develop` (**Merge commit**) → validar → PR `develop → main` (**Merge commit, nunca squash**) → back-merge `main → develop` → tag.
- **Por qué merge commit entre `develop` y `main`:** con squash las ramas divergen y aparecen conflictos fantasma.
- **Commits:** *Conventional Commits* (`tipo(alcance): descripción`), atómicos y con `git add` explícito (nunca `git add .`, para no colar `.env`).
- **Orden de despliegue:** si el release toca ambos repos, **primero backend** (migración manual → merge → Render `Live` → smoke test) y **luego frontend**.
- **Release actual:** `v0.2.0` (mismo tag en ambos repos).
- **Protección de ramas:** exigir PR y que pasen los checks (`test` en backend, `lint-and-build` en frontend).

---

## 4. Entorno local (Docker)

`docker-compose.yml` define tres servicios: `backend` (puerto 8000), `frontend` (5173) y `db` (Postgres 15, puerto 5432, con volumen `postgres_data`).

**Regla de oro: todo `python manage.py ...` se ejecuta DENTRO del contenedor `backend`**, no en el Python de Windows (no tiene las dependencias y es 3.10 frente a 3.11 del proyecto).

**Forzar siempre la BD local en tests y migraciones** (el `.env` del backend puede apuntar a Supabase; un test corrió una vez contra la nube por eso):

```bash
docker compose exec -e POSTGRES_HOST=db -e POSTGRES_PORT=5432 -e POSTGRES_DB=habitdb -e POSTGRES_USER=habituser -e POSTGRES_PASSWORD=habitpass backend python manage.py test habits -v 2 --noinput
docker compose exec -e POSTGRES_HOST=db -e POSTGRES_PORT=5432 -e POSTGRES_DB=habitdb -e POSTGRES_USER=habituser -e POSTGRES_PASSWORD=habitpass backend python manage.py makemigrations --check --dry-run
```

- La BD de pruebas se llama `test_habitdb`. Si aparece `test_postgres`, los tests están apuntando a Supabase: parar.
- `python manage.py check` detecta en segundos errores de URLs/vistas (un typo `url=` en `@action` tumbó todo el router).
- Frontend: `npm run lint` y `npm run build` (en la carpeta del frontend).
- Logs del backend: `docker compose logs backend --tail 60`.
- Aviso inofensivo: `The "z" variable is not set` viene de un `$` sin escapar en algún `.env`/compose (pendiente menor de revisar).
- Si cambia `@theme` o variables `VITE_*`, reiniciar el contenedor del frontend (Vite las lee al arrancar).

---

## 5. Backend: modelo de dominio

Modelos en `habits/models.py`:

- **`CustomUser`** (extiende `AbstractUser`): `email` único y opcional. **Invariante: sin email se guarda `NULL`, nunca `""`** (el `save()` lo fuerza; en Postgres un `UNIQUE` admite varios `NULL` pero un solo `""`). Métodos `current_streak()` y `monthly_completion_rate()`.
- **`Category`**: `user`, `name`, `color` (hex), `unique_together (user, name)`. Al borrarla, los hábitos quedan sin categoría (`SET_NULL`).
- **`Habit`**: `user`, `name`, `description`, `category`, `frequency` (daily/weekly/monthly, **aún sin efecto real**), `target_per_period` (meta por día), `unique_together (user, name)`. Métodos `current_streak()`, `week_history()`, `completion_rate()`.
- **`HabitRecord`**: un registro por hábito y día (`date` es `DateTimeField` a medianoche, por eso se filtra con `date__date`), `completed`, `completed_at`, `progress` (contador cuando la meta > 1), `note`.
- **`Progress`**: `user`, `habit` (nullable: `NULL` = progreso **global**), `level`, `experience`. Restricciones únicas **parciales** (migración `0005`): un progreso por (usuario, hábito) y **un solo progreso global por usuario**. Se necesitan porque en SQL `NULL != NULL` y `unique_together` no protege el caso global.

**Reglas de negocio vigentes:**

- XP al completar un hábito: **+20 global, +25 hábito**. Al desmarcar se restan (mínimo 0) pero **no se baja de nivel**.
- XP para subir de nivel: `nivel × 100`.
- **Racha con tolerancia:** un día aislado fallado no la rompe; **dos seguidos sí**. Si hoy aún no se completó, no se penaliza: se evalúa desde ayer.
- "Racha en riesgo" (frontend): racha > 0, hoy no completado y ayer tampoco; se muestra **todo el día**, no solo por la noche.
- `TIME_ZONE = America/Bogota`, `USE_TZ = True`.

---

## 6. Backend: API

Base: `/api/`. Autenticación **JWT** (SimpleJWT): access 30 min, refresh 1 día. Sin credenciales: **401**.

| Endpoint | Métodos | Notas |
|---|---|---|
| `/token/`, `/token/refresh/` | POST | Login y renovación |
| `/register/` | **solo POST** | Público. Valida contraseña en el servidor, normaliza email (`""` → `NULL`, minúsculas, único sin distinguir mayúsculas). No hay list/detalle |
| `/categories/` | CRUD | Filtrado por usuario. Nombre único por usuario sin distinguir mayúsculas |
| `/habits/` | CRUD | Filtrado por usuario. `validate_name` rechaza duplicados (400); un `IntegrityError` concurrente también se convierte en 400 |
| `/habits/today/` | GET | Hábitos con registro del día, racha, historial 7 días, progreso. **Hoy escribe registros (ver pendientes)** |
| `/habits/{id}/toggle-completion/` | POST | Marca/desmarca; atómico con `select_for_update`; da XP |
| `/habits/{id}/update-progress/` | POST | `direction: increment|decrement` para metas > 1 |
| `/progress/global/` | GET | Solo lectura. Usuario sin progreso: 200 con nivel 1 / 0 XP **sin escribir** |
| `/progress/{habit_id}/habit-progress/` | GET | Solo lectura. Hábito inexistente o ajeno: **404** (no revela existencia) |
| `/progress/` y `/progress/{id}/` | solo lectura | `POST/PATCH/DELETE` → **405**. `list` devuelve 404 si está vacío (pendiente: debería ser 200 `[]`) |
| `/habit-record/` | CRUD | Existe pero el frontend no lo usa |

**Decisiones de seguridad ya tomadas:**

- Mínimo privilegio: cada viewset expone solo las operaciones de su caso de uso (`RegisterViewSet` = `CreateModelMixin`; `ProgressViewSet` = list + retrieve).
- **El XP lo calcula siempre el servidor.** `ProgressSerializer` expone solo `habit, level, experience, xp_to_next` y todo es `read_only`.
- Recursos ajenos devuelven **404, no 403**.
- La restricción de propiedad va **dentro de la consulta** (`get_object_or_404(Habit, pk=pk, user=request.user)`), no en un `if` posterior.
- Los `GET` no deben escribir en la BD.
- Los invariantes de datos se protegen en la capa más baja (modelo/BD), no solo en el serializer.
- No devolver `str(e)` de excepciones internas al cliente.

---

## 7. Backend: pruebas y CI

- Tests en `habits/tests.py` (**24 en verde**): `RegisterEndpointTests`, `ProgressSecurityTests`, `HabitNameTests`, `GlobalProgressNewUserTests`.
- Cubren seguridad del registro, solo lectura del progreso, IDOR, nombres duplicados y unicidad del progreso global. **No hay aún tests de CRUD de categorías, `today`, `update-progress` ni rachas/XP.**
- Patrón de test: Arrange–Act–Assert; verificar la respuesta **y** el estado de la BD (`refresh_from_db()`); crear usuarios con `create_user` y el resto con `create`.
- **CI** (`.github/workflows/backend-ci.yml`): Ubuntu + Postgres 15 como servicio con healthcheck; pasos `manage.py check` → `makemigrations --check --dry-run` → `manage.py test habits`. Variables falsas de CI (nunca se toca Supabase). Acciones fijadas a versión mayor; `permissions: contents: read`.
- **Regla:** si cambias un modelo, **incluye la migración en el commit** o el CI falla.

---

## 8. Frontend: estructura y decisiones

```
src/
├── api/axios.js            # Instancia de Axios + interceptores (token y refresh)
├── context/                # auth-context.js (solo el contexto) y AuthContext.jsx (AuthProvider)
├── hooks/                  # useAuth, useIdleSession, useNow
├── utils/                  # session.js, apiErrors.js, habitUtils.js
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
- **Estado derivado se calcula, no se guarda** (las estadísticas de "Hoy" salen de `habits`).
- Los updaters de `setState` son puros (sin efectos dentro).
- La fuente de verdad tras crear/editar es el servidor (`fetchHabits()`).
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
- El historial de 7 días se rotula con letras calculadas desde la fecha real (el backend devuelve los 7 días que terminan **hoy**).
- Dashboard: saludo por hora, fecha y reloj (`useNow`, aislado en un componente pequeño), tres métricas compactas en fila también en móvil, tarjeta de nivel/XP.
- Accesibilidad: etiquetas con `htmlFor`, `aria-*`, foco visible, modales con `Escape`, clic fuera y X.

**CI** (`.github/workflows/frontend-ci.yml`): `npm ci` → `npm run lint` → `npm run build`, con Node 20 y `VITE_API_URL` falso. Lint en **0 errores y 0 warnings**. `eslint.config.js` usa `varsIgnorePattern` y `argsIgnorePattern` con `^[A-Z_]` porque ESLint base no reconoce el JSX como uso.

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

---

## 10. Pendientes

> Los pendientes **compartidos** aparecen en las dos listas (marcados con 🔗). Al cerrarlos, se borran de ambas.

### 10.1 Backend

**Funcionalidad**
- 🔗 **`feat/habit-frequency`:** hoy `frequency` (semanal/mensual) existe pero ninguna lógica la usa y la UI siempre dice "Meta por día". Requiere decidir cómo se calculan "completado", rachas y XP por periodo, con migración y tests primero. Es la funcionalidad más delicada.

**Seguridad y despliegue**
- 🔗 **Blacklist del refresh token** en el logout (`rest_framework_simplejwt.token_blacklist`): hoy el logout solo borra `localStorage` y el refresh sigue válido hasta 1 día.
- 🔗 **`migrate` automático en el despliegue** (PR de DevOps): p. ej. `CMD ["sh","-c","python manage.py migrate --noinput && gunicorn ..."]` en `Dockerfile.prod`, o Pre-Deploy si el plan lo permite.
- 🔗 **CORS:** `CORS_ALLOW_ALL_ORIGINS = True`; restringir al dominio de Netlify y a localhost.
- `ALLOWED_HOSTS` con `.split(",")` sobre `""` da `['']`; limpiar.
- Contenedor de producción corre como **root**; crear usuario sin privilegios.
- Separar proyectos de Supabase de **dev y prod**.
- Logging estructurado y monitoreo (Sentry).

**Arquitectura y calidad**
- **`GET /habits/today/` escribe en la BD** (crea un `HabitRecord` por hábito y día). Debe ser seguro: *ausencia de registro = no completado*. Mismo patrón que ya aplicamos al progreso.
- **N+1 queries:** `today` hace ~6-8 consultas por hábito (record, ayer, progress, racha, historial, categoría). Resolver con `select_related`/`prefetch_related`/anotaciones.
- **Dos representaciones del hábito** (el dict armado a mano en `today` y `HabitSerializer`, con `get_completed_today` comparando `DateTimeField` con una fecha). Unificar en un serializer.
- **Capa de servicios** (`habits/services.py`): hoy el XP vive en las vistas (20/25), en `Habit.mark()` (10) y la racha está duplicada entre `CustomUser` y `Habit`. Centralizar con funciones puras y testeables.
- **`HabitRecord.date` como `DateTimeField`** a medianoche obliga a `date__date` y produce el warning de datetime naive. Evaluar `DateField` (y zona horaria por usuario).
- **Exploit de XP:** marcar/desmarcar sube niveles pero nunca los baja. Resolver con un historial de eventos de XP (ledger).
- `toggle-completion` en hábitos con meta > 1 marca `completed` sin actualizar `progress` (datos inconsistentes).
- `ProgressViewSet.list` devuelve 404 con colección vacía; debería ser 200 con `[]`.
- `habits/apps.py` (`ready()` fuera de la clase) y `habits/signals.py` (sobre `User`, no `CustomUser`) son **código muerto**: eliminar.
- Validar `target_per_period >= 1` (`MinValueValidator`).
- Evaluar si `HabitRecordViewSet` se usa; si no, retirarlo (superficie de ataque).
- Menores: `STATICFILES_STORAGE` obsoleto (usar `STORAGES`), `AUTH_PASSWORD_VALIDATORS` duplicado, `select_related` → `list_select_related` y typo `select_relate` en el admin, mezcla de `config()` y `os.getenv` para la BD, paginación.
- **Más tests:** categorías, `today`, `update-progress`, rachas y XP, `monthly_completion_rate`.

### 10.2 Frontend

**Funcionalidad**
- 🔗 **`feat/habit-frequency`:** adaptar el modal ("Meta por día" → según frecuencia), tarjetas, métricas y la lógica de "racha en riesgo" al modelo nuevo del backend.

**Seguridad y despliegue**
- 🔗 **Blacklist del refresh token:** en el logout, llamar al endpoint del backend antes de limpiar el `localStorage`.
- 🔗 **Cabeceras de seguridad** con `public/_headers` (`X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` o CSP) y mantener coherencia con el CORS del backend.
- 🔗 **`migrate` automático:** sin cambios en este repo, pero el orden de despliegue (backend antes que frontend) debe respetarse.
- Tokens en `localStorage` (riesgo XSS): evaluar cookie `httpOnly` para el refresh token.

**Arquitectura y calidad**
- **TanStack Query** para los datos del servidor: eliminaría fetches manuales, estados de carga y actualizaciones optimistas hechas a mano.
- Extraer un hook `useHabits` de `HabitList` (mezcla UI, HTTP y lógica).
- **Tests de frontend** (Vitest + Testing Library): hoy la red de seguridad es el lint, el build y la prueba manual.
- **Dockerfiles:** usar `npm ci` en lugar de `npm install --force` (oculta conflictos de dependencias) y producción multi-etapa (build con Node, servir con nginx).
- El toast "+XP" muestra el XP acumulado, no el ganado (decisión: se deja así por ahora).
- Acciones de GitHub Actions: `actions/checkout@v4` y `setup-python@v5` avisan por Node 20 deprecado; revisar las versiones mayores vigentes antes de subir. `ubuntu-latest` migra a Ubuntu 26 en octubre de 2026 (el frontend ya fija `ubuntu-24.04`; unificar en el backend).
- Revisar que `HabitCard` y `HabitModal` mantengan accesibilidad con teclado en el menú ⋮.

**Producto (ideas por definir)**
- Pendiente de recopilar nuevas funcionalidades; con el sistema de diseño ya montado, cada pantalla nueva debe reutilizar `btn`, `field`, `card`, `Modal` y `ConfirmDialog`.

---

## 11. Cómo usar este documento en una conversación nueva con Claude

1. Pega este archivo completo al empezar el chat.
2. Indica **la rama o tarea** (p. ej. `feat/habit-frequency`) y sube **solo los archivos que se van a tocar** (`models.py`, `views.py`, `HabitCard.jsx`...).
3. Recuerda el modo de trabajo: mentor, archivos completos, tests primero, mobile first.
4. Al terminar el trabajo, **actualiza este documento** en el mismo PR (borra los pendientes cerrados, añade decisiones y lecciones) y cópialo idéntico al otro repo.
