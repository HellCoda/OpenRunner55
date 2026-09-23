#!/usr/bin/env bash
# build-appimage.sh — Construit OpenRunner55-x86_64.AppImage (ADR-009).
#
# Bundle autonome : Python 3.14 (stdlib + interpéteur), GTK4, libadwaita,
# libsecret, libudev (systemd-libs), libgirepository, et dépendances transitives.
#
# Usage : ./scripts/build-appimage.sh
# Sortie : dist/OpenRunner55-x86_64.AppImage
#
# Prérequis (Fedora) : python3, pip, dnf install python3-gobject gtk4 libadwaita
# libsecret systemd-libs gobject-introspection-devel (pour les typelibs).
# appimagetool est téléchargé automatiquement si absent.
set -euo pipefail

# --- Configuration -----------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="OpenRunner55"
APP_LOWER="openrunner55"
APP_VERSION="$(python3 -c "import tomllib,sys; print(tomllib.load(open(f'{sys.argv[1]}/pyproject.toml','rb'))['project']['version'])" "$REPO_ROOT")"
ARCH="x86_64"
APPIMAGE_NAME="${APP_NAME}-${ARCH}.AppImage"
BUILD_DIR="${REPO_ROOT}/build/appimage"
APPDIR="${BUILD_DIR}/AppDir"
DIST_DIR="${REPO_ROOT}/dist"
APPIMAGETOOL_DIR="${REPO_ROOT}/build/tools"
APPIMAGETOOL="${APPIMAGETOOL_DIR}/appimagetool"

PYTHON_BIN="$(command -v python3)"
PYTHON_VERSION="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PYTHON_ABI="$("$PYTHON_BIN" -c 'import sysconfig; print(sysconfig.get_config_var("EXT_SUFFIX"))' | sed 's/^\.//; s/\.so$//')"

# Répertoires système (Fedora 44 : lib64)
LIBDIR="/usr/lib64"
GI_REPODIR="${LIBDIR}/girepository-1.0"
SCHEMAS_DIR="/usr/share/glib-2.0/schemas"
PIXBUF_DIR="${LIBDIR}/gdk-pixbuf-2.0/2.10.0"
STDLIB_DIR="${LIBDIR}/python${PYTHON_VERSION}"

# Couleurs/logs
log()  { printf '\033[1;34m[build]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; }

# --- Préparation -------------------------------------------------------------
cleanup() { rm -rf "$APPDIR"; }
trap cleanup EXIT
mkdir -p "$BUILD_DIR" "$DIST_DIR" "$APPIMAGETOOL_DIR"
cleanup
mkdir -p "$APPDIR"/usr/{bin,lib,lib64,share} "$APPDIR/usr/lib/python${PYTHON_VERSION}/site-packages"

log "Construction ${APPIMAGE_NAME} v${APP_VERSION} (Python ${PYTHON_VERSION})"

# --- appimagetool ------------------------------------------------------------
fetch_appimagetool() {
    if [[ -x "$APPIMAGETOOL" ]]; then return 0; fi
    log "Téléchargement d'appimagetool (binaire statique officiel)…"
    local url="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    curl -fsSL "$url" -o "$APPIMAGETOOL"
    chmod +x "$APPIMAGETOOL"
    # appimagetool est lui-même une AppImage : on l'extrait pour obtenir le binaire.
    if ! "$APPIMAGETOOL" --version >/dev/null 2>&1; then
        warn "appimagetool ne s'exécute pas directement (FUSE ?). Extraction…"
        local extract_dir="${APPIMAGETOOL_DIR}/extracted"
        rm -rf "$extract_dir"; mkdir -p "$extract_dir"
        ( cd "$extract_dir" && "$APPIMAGETOOL" --appimage-extract >/dev/null 2>&1 ) || true
        if [[ -f "$extract_dir/squashfs-root/AppRun" ]]; then
            cp -r "$extract_dir/squashfs-root"/* "$APPIMAGETOOL_DIR"/
            mv "$APPIMAGETOOL" "${APPIMAGETOOL}.orig"
            cp "$APPIMAGETOOL_DIR/AppRun" "$APPIMAGETOOL"
            chmod +x "$APPIMAGETOOL"
        fi
    fi
    "$APPIMAGETOOL" --version >/dev/null 2>&1 || { err "appimagetool inutilisable"; exit 1; }
}
fetch_appimagetool

# --- Helpers : copie récursive des bibliothèques -----------------------------
# Liste des libs déjà copiées (pour éviter les doublons / boucles).
declare -A COPIED_LIBS

# Patterns de libs système à NE PAS bundler (glibc core + dynamic linker).
# On garde tout le reste pour maximiser la portabilité.
is_excluded_lib() {
    local lib="$1"
    case "$(basename "$lib")" in
        ld-linux*|ld-*.so*|libc.so*|libm.so*|libdl.so*|libpthread.so*|librt.so*|\
        libutil.so*|libresolv.so*|libanl.so*|libBrokenLocale.so*|libnss_*|\
        libcidn.so*|libcrypt.so*|libmemusage.so*|libSegFault.so*)
            return 0 ;;
    esac
    return 1
}

copy_lib_recursive() {
    # $1 = chemin absolu de la lib à copier (puis résout ses dépendances).
    local lib="$1"
    [[ -f "$lib" ]] || return 0
    local base="$(basename "$lib")"
    # Dédoublonnage par basename (les libs sont copiées à plat dans usr/lib).
    if [[ -n "${COPIED_LIBS[$base]:-}" ]]; then return 0; fi
    COPIED_LIBS[$base]=1
    is_excluded_lib "$lib" && return 0
    cp -L "$lib" "$APPDIR/usr/lib/" 2>/dev/null || return 0
    # Résout les dépendances transitives.
    local dep
    while IFS= read -r line; do
        dep="$(awk '{print $3}' <<<"$line")"
        [[ -z "$dep" || "$dep" == "=>" || "$dep" == "not" ]] && continue
        [[ -f "$dep" ]] && copy_lib_recursive "$dep"
    done < <(ldd "$lib" 2>/dev/null)
}

# --- 1. Runtime Python : interpréteur + stdlib + libpython -------------------
log "Bundling Python ${PYTHON_VERSION} (interpréteur + stdlib)…"
cp -L "$PYTHON_BIN" "$APPDIR/usr/bin/python${PYTHON_VERSION}"
ln -sf "python${PYTHON_VERSION}" "$APPDIR/usr/bin/python3"
ln -sf "python${PYTHON_VERSION}" "$APPDIR/usr/bin/python"

# libpython
copy_lib_recursive "${LIBDIR}/libpython${PYTHON_VERSION}.so.1.0"

# Stdlib : copie puis nettoyage (tests, __pycache__, ensurepip, idlelib…).
# Fedora place la stdlib dans lib64/ (platlibdir=lib64) — on respecte ce layout
# pour que PYTHONHOME=usr la trouve.
cp -a "${STDLIB_DIR}/." "$APPDIR/usr/lib64/python${PYTHON_VERSION}/"
rm -rf "$APPDIR/usr/lib64/python${PYTHON_VERSION}"/{test,tests,__pycache__,idlelib,tkinter,ensurepip,venv}
find "$APPDIR/usr/lib64/python${PYTHON_VERSION}" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "$APPDIR/usr/lib64/python${PYTHON_VERSION}" -name '*.pyc' -delete 2>/dev/null || true

# --- 2. Module gi (PyGObject) système : copie du package + ses .so ----------
log "Bundling PyGObject (gi) depuis le système…"
GI_SRC="${LIBDIR}/python${PYTHON_VERSION}/site-packages/gi"
cp -a "$GI_SRC" "$APPDIR/usr/lib/python${PYTHON_VERSION}/site-packages/gi"
# Dépendances natives du module gi.
copy_lib_recursive "${GI_SRC}/_gi.cpython-${PYTHON_VERSION}-x86_64-linux-gnu.so"
copy_lib_recursive "${GI_SRC}/_gi_cairo.cpython-${PYTHON_VERSION}-x86_64-linux-gnu.so"
# libgirepository (Fedora 44 : libgirepository-2.0.so.0)
copy_lib_recursive "${LIBDIR}/libgirepository-2.0.so.0"

# --- 3. Dépendances pip (hors PyGObject, fourni par le système) -------------
log "Installation des dépendances pip (garminconnect, secretstorage, pyudev + transitives)…"
"$PYTHON_BIN" -m pip install --no-cache-dir \
    --target="$APPDIR/usr/lib/python${PYTHON_VERSION}/site-packages" \
    "garminconnect==0.3.9" "secretstorage>=3.5" "pyudev>=0.24"

# --- 4. Package applicatif openrunner55 --------------------------------------
log "Installation du package openrunner55…"
"$PYTHON_BIN" -m pip install --no-cache-dir --no-deps \
    --target="$APPDIR/usr/lib/python${PYTHON_VERSION}/site-packages" \
    "$REPO_ROOT"

# --- 5. Bibliothèques système : GTK4, libadwaita, libsecret, libudev --------
log "Bundling GTK4, libadwaita, libsecret, libudev (+ dépendances transitives)…"
for lib in \
    "${LIBDIR}/libgtk-4.so.1" \
    "${LIBDIR}/libadwaita-1.so.0" \
    "${LIBDIR}/libsecret-1.so.0" \
    "${LIBDIR}/libudev.so.1"; do
    copy_lib_recursive "$lib"
done

# --- 6. Typelibs (GI_TYPELIB_PATH) -------------------------------------------
log "Copie des typelibs GObject Introspection…"
mkdir -p "$APPDIR/usr/lib/girepository-1.0"
cp -a "${GI_REPODIR}/." "$APPDIR/usr/lib/girepository-1.0/"

# --- 7. Schemas GSettings (libadwaita + gtk4 + desktop) ---------------------
log "Copie et compilation des schemas GSettings…"
mkdir -p "$APPDIR/usr/share/glib-2.0/schemas"
cp -a "${SCHEMAS_DIR}/." "$APPDIR/usr/share/glib-2.0/schemas/"
# Recompilation locale pour garantir la cohérence.
if command -v glib-compile-schemas >/dev/null 2>&1; then
    glib-compile-schemas "$APPDIR/usr/share/glib-2.0/schemas/" 2>/dev/null || \
        warn "glib-compile-schemas a échoué (on conserve gschemas.compiled système)"
else
    warn "glib-compile-schemas absent — gschemas.compiled système conservé"
fi

# --- 8. Pixbuf loaders (GDK_PIXBUF_MODULE_FILE) ------------------------------
log "Copie des pixbuf loaders…"
mkdir -p "$APPDIR/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders"
cp -a "${PIXBUF_DIR}/loaders/." "$APPDIR/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders/" 2>/dev/null || warn "Aucun loader pixbuf trouvé"
# Cache loaders : régénéré côté runtime si absent ; on tente une copie.
cp -L "${PIXBUF_DIR}/loaders.cache" "$APPDIR/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache" 2>/dev/null || \
    warn "loaders.cache pixbuf absent"

# --- 9. Ressources GTK4 (schemas compilés déjà copiés ; fonts/icônes système) -
# GTK4 utilise les thèmes/icônes système : on ne bundle pas (trop volumineux,
# et l'AppImage s'exécute sur l'hôte qui fournit son thème).

# --- 10. Fichier .desktop + icône (racine AppDir) ---------------------------
log "Installation du .desktop et de l'icône…"
cp "$REPO_ROOT/assets/openrunner55.desktop" "$APPDIR/${APP_LOWER}.desktop"
cp "$REPO_ROOT/assets/openrunner55.png" "$APPDIR/${APP_LOWER}.png"

# --- 11. AppRun --------------------------------------------------------------
log "Écriture de AppRun…"
cat > "$APPDIR/AppRun" <<APPRUN
#!/usr/bin/env bash
# AppRun — OpenRunner55. Configure l'environnement puis lance l'application.
set -e
HERE="\$(dirname "\$(readlink -f "\$0")")"

# Bibliothèques bundlées.
export LD_LIBRARY_PATH="\${HERE}/usr/lib\${LD_LIBRARY_PATH:+:\${LD_LIBRARY_PATH}}"

# Python : interpréteur + stdlib + site-packages bundlés.
export PYTHONHOME="\${HERE}/usr"
export PYTHONPATH="\${HERE}/usr/lib/python${PYTHON_VERSION}/site-packages"

# GObject Introspection : typelibs.
export GI_TYPELIB_PATH="\${HERE}/usr/lib/girepository-1.0"

# GSettings : schemas compilés.
export GSETTINGS_SCHEMA_DIR="\${HERE}/usr/share/glib-2.0/schemas"

# GdkPixbuf : loaders.
export GDK_PIXBUF_MODULE_FILE="\${HERE}/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache"
export GDK_PIXBUF_MODULEDIR="\${HERE}/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders"

# GTK4 : on force le backend Wayland/X11 selon la session, et on désactive
# l'accès au portal de sandbox (l'AppImage n'est pas sandboxée).
export GTK_EXE_NAME="${APP_LOWER}"
# Les répertoires de données utilisateur restent ceux de l'hôte (~/.local/share).

exec "\${HERE}/usr/bin/python${PYTHON_VERSION}" -m openrunner55 "\$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# --- 12. Empaquetage ---------------------------------------------------------
log "Empaquetage avec appimagetool…"
cd "$BUILD_DIR"
VERSION="${APP_VERSION}" "$APPIMAGETOOL" --no-appstream "$APPDIR" "${DIST_DIR}/${APPIMAGE_NAME}"

log "Terminé : ${DIST_DIR}/${APPIMAGE_NAME}"
ls -lh "${DIST_DIR}/${APPIMAGE_NAME}"
