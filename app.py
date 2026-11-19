import json
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from local_video import servir_video
from tracking_catalog import read_tracking_header
from video_jobs import get_video_job, submit_video_job

try:
    from video_track import analyze_video_full, parse_mmss
except Exception as error:
    VIDEO_DISPONIBLE = False
    VIDEO_ERROR = str(error)
else:
    VIDEO_DISPONIBLE = True
    VIDEO_ERROR = ""

st.set_page_config(page_title="Análisis de vídeo", layout="wide")
st.title("Análisis de vídeo")


@st.cache_resource(show_spinner=False, max_entries=2)
def cargar_tracking_json(ruta_str, mtime):
    with open(ruta_str, encoding="utf-8") as archivo:
        return json.load(archivo)


carpeta_app = Path(__file__).resolve().parent
ruta_gen = st.session_state.get("video_gen_path", "")
tracking_actual = st.session_state.get("tracking_del_video", "")
listo = bool(
    ruta_gen and os.path.isfile(ruta_gen)
    and st.session_state.get("mv_video_ready_path") == ruta_gen
    and tracking_actual and os.path.isfile(tracking_actual)
)

# Evita renderizar información de otro partido, incluso si quedó
# en la sesión o en la carpeta tras un análisis anterior.
if listo:
    try:
        cabecera_actual = read_tracking_header(Path(tracking_actual))
        nombre_tracking = cabecera_actual.get("video_filename")
        if nombre_tracking and nombre_tracking != Path(ruta_gen).name:
            listo = False
            st.session_state.pop("mv_video_ready_path", None)
    except (ValueError, OSError, TypeError):
        listo = False
        st.session_state.pop("mv_video_ready_path", None)

trabajo_id = st.session_state.get("mv_video_job")
trabajo = get_video_job(trabajo_id) if trabajo_id else None

if not listo and trabajo and trabajo["state"] in ("queued", "running", "completed"):
    # El formulario desaparece durante el procesamiento; sólo hay
    # progreso y, al terminar, el analizador de Match View.
    @st.fragment(run_every=2)
    def progreso_match_view():
        estado = get_video_job(st.session_state.get("mv_video_job"))
        if not estado:
            st.error("El proceso ya no está disponible. Inicia otro análisis.")
            st.session_state.pop("mv_video_job", None)
            return
        st.markdown("### Analizando vídeo")
        st.progress(float(estado.get("progress") or 0.0))
        st.caption(estado.get("message") or "Procesando vídeo…")
        if estado["state"] == "queued":
            st.caption("Esperando al trabajo de vídeo anterior.")
        if estado["state"] == "failed":
            st.error("Error durante el análisis: " + str(estado.get("error")))
            st.session_state.pop("mv_video_job", None)
            return
        if estado["state"] == "completed":
            try:
                resultado = estado.get("result") or {}
                st.session_state["mv_model_status"] = resultado.get("model_status", {})
                generado = resultado.get("tracking_json")
                if not generado or not os.path.isfile(generado):
                    raise ValueError("El análisis terminó sin generar tracking.")
                st.session_state["tracking_del_video"] = str(generado)
                st.session_state["video_analizado_path"] = ruta_gen
                st.session_state["mv_video_ready_path"] = ruta_gen
                st.session_state.pop("mv_video_job", None)
                st.rerun()
            except (OSError, ValueError, TypeError) as error:
                st.session_state.pop("mv_video_job", None)
                st.error(f"No se pudo abrir el tracking generado: {error}")
    progreso_match_view()
elif not listo:
    st.markdown("### Análisis de vídeo")
    if trabajo and trabajo["state"] == "failed":
        st.error("El último análisis falló: "
                 + str(trabajo.get("error") or "Error desconocido")
                 + ". Revisa la ruta y vuelve a intentarlo.")
    with st.form("mv_video_start_form", clear_on_submit=False):
        c1, c2, c3 = st.columns([3, 1, 1.5])
        with c1:
            ruta_form = st.text_input(
                "Ruta local del vídeo",
                value=ruta_gen,
                placeholder=r"C:\Videos\partido.mp4",
            )
        with c2:
            saque_form = st.text_input(
                "Iniciar análisis en (min o MM:SS)",
                value=st.session_state.get("video_gen_kickoff", "00:00"),
                help="Minuto del archivo de vídeo donde comienza el análisis. "
                     "Ejemplo: 15 o 15:00 empieza en el minuto 15; 15:30 empieza en 15:30.",
            )
        with c3:
            alcance_form = st.selectbox(
                "Alcance",
                ["10 minutos desde el inicio indicado", "Hasta el final del vídeo"],
                index=0 if st.session_state.get("video_gen_alcance",
                              "10 minutos desde el inicio indicado") in ("Primeros 10 minutos (prueba)", "10 minutos desde el inicio indicado")
                        else 1,
            )
        st.caption("Modo automático: se utilizan los modelos disponibles y los respaldos "
                   "necesarios. Los componentes no disponibles se indicarán al terminar.")
        iniciar = st.form_submit_button(
            "Analizar vídeo", type="primary", use_container_width=False,
        )
    if iniciar:
        ruta_form = ruta_form.strip().strip('"').strip("'").strip()
        if not ruta_form or not os.path.isfile(ruta_form):
            st.error("Introduce la ruta de un vídeo existente en este equipo.")
        elif not VIDEO_DISPONIBLE:
            st.error(f"No se puede iniciar YOLO: {VIDEO_ERROR}")
        else:
            try:
                saque_segundos = parse_mmss(saque_form)
                if saque_segundos is None or saque_segundos < 0:
                    raise ValueError("Inicio del análisis inválido.")
            except (ValueError, TypeError):
                st.error("Indica un minuto válido: 15, 15:00 o 15:30. No se admiten tiempos negativos.")
            else:
                st.session_state["video_gen_path"] = ruta_form
                st.session_state["video_gen_kickoff"] = saque_form
                st.session_state["video_gen_alcance"] = alcance_form
                st.session_state.pop("mv_video_ready_path", None)
                st.session_state.pop("tracking_del_video", None)
                parametros = {
                    "video_path": Path(ruta_form),
                    "sample_fps": 10,
                    "min_confidence": 0.65,
                    "yolo_model": str(carpeta_app / "modelo_propio.pt"),
                    "auto_models": True,
                    "max_minutes": 10.0 if alcance_form.startswith(("Primeros", "10 minutos")) else None,
                    "kickoff_offset": saque_segundos,
                    "camera_mode": "seguimiento",
                    "device": "cpu",
                }
                if hasattr(st, "fragment"):
                    st.session_state["mv_video_job"] = submit_video_job(
                        analyze_video_full, parametros,
                    )
                    st.rerun()
                else:
                    barra = st.progress(0.0)
                    mensaje = st.empty()
                    def actualizar_progreso(texto, fraccion):
                        barra.progress(max(0.0, min(1.0, float(fraccion))))
                        mensaje.caption(texto)
                    try:
                        resultado = analyze_video_full(
                            **parametros, progress=actualizar_progreso,
                        )
                        st.session_state["mv_model_status"] = resultado.get("model_status", {})
                        generado = resultado.get("tracking_json")
                        if not generado or not os.path.isfile(generado):
                            raise ValueError("No se generó el tracking.")
                        st.session_state["tracking_del_video"] = str(generado)
                        st.session_state["video_analizado_path"] = ruta_form
                        st.session_state["mv_video_ready_path"] = ruta_form
                        st.rerun()
                    except Exception as error:
                        st.error(f"No se pudo analizar el vídeo: {error}")
else:
    # Solamente Match View / Vídeo tras finalizar el tracking.
    ruta_pantalla = carpeta_app / "analizador_video.html"
    if not ruta_pantalla.is_file():
        st.error("No se encontró analizador_video.html junto a app.py.")
    else:
        html_pantalla = ruta_pantalla.read_text(encoding="utf-8")
        try:
            pista = Path(tracking_actual)
            datos_tracking = cargar_tracking_json(
                str(pista), pista.stat().st_mtime,
            )
            model_status = datos_tracking.get("model_status") or st.session_state.get("mv_model_status", {})
            model_names = {"base": "modelo base", "yolov9": "YOLOv9", "rfdetr": "RF-DETR",
                           "pitch32": "campo (32 puntos)", "pitch_legacy": "campo anterior",
                           "actions": "OpenSportsLab", "gamestate": "SoccerNet Game State"}
            active = [model_names.get(name, name) for name, item in model_status.items()
                      if item.get("state") == "active"]
            skipped = [model_names.get(name, name) for name, item in model_status.items()
                       if item.get("state") in ("error", "unavailable")]
            if active:
                st.caption("Componentes cargados: " + ", ".join(active))
            if skipped:
                st.caption("Componentes omitidos: " + ", ".join(skipped))
            start_s = datos_tracking.get("analysis_start_s", datos_tracking.get("kickoff_s", 0))
            end_s = datos_tracking.get("analysis_end_s")
            if end_s is not None:
                st.caption(f"Intervalo analizado del vídeo: {int(start_s//60):02d}:{int(start_s%60):02d} "
                           f"a {int(end_s//60):02d}:{int(end_s%60):02d}.")
            with st.expander("Buscar jugadas IA", expanded=False):
                st.caption("Busca posibles goles y otras acciones sin repetir el seguimiento. Los tiempos corresponden al vídeo original.")
                scan_end = float(end_s) if end_s is not None else float(start_s) + float(datos_tracking.get("match_duration_s", 0))
                with st.form("mv_rescan_actions"):
                    scan_start = st.number_input("Desde (segundos del vídeo)", min_value=float(start_s), max_value=scan_end, value=float(start_s), step=1.0)
                    scan_stop = st.number_input("Hasta (segundos del vídeo)", min_value=float(start_s), max_value=scan_end, value=scan_end, step=1.0)
                    scan_actions = st.form_submit_button("Buscar jugadas en este tramo")
                if scan_actions:
                    try:
                        from action_review import analyze_saved_actions
                        with st.spinner("Buscando jugadas en el fragmento…"):
                            proposals = analyze_saved_actions(pista, ruta_gen, scan_start, scan_stop)
                        st.session_state["mv_actions_result"] = f"Búsqueda completada: {len(proposals)} propuestas en el tramo seleccionado."
                        st.rerun()
                    except Exception:
                        import logging
                        logging.getLogger(__name__).exception("Action rescan failed")
                        st.error("No se pudo completar la búsqueda de jugadas. Comprueba la preparación del motor de acciones.")
                if st.session_state.get("mv_actions_result"):
                    st.info(st.session_state.pop("mv_actions_result"))
            if "suggested_events" not in datos_tracking:
                from event_candidates import suggest_key_moments
                datos_tracking = dict(datos_tracking)
                datos_tracking["suggested_events"] = suggest_key_moments(
                    datos_tracking.get("samples") or [],
                    kickoff_s=float(datos_tracking.get("kickoff_s") or 0),
                )
            from playback_media import prepare_playback_clip
            sample_times = [sample["t"] for sample in datos_tracking.get("samples", [])]
            start_s = datos_tracking.get("analysis_start_s", datos_tracking.get("kickoff_s", 0))
            end_s = datos_tracking.get("analysis_end_s")
            if end_s is None:
                duration_s = datos_tracking.get("match_duration_s")
                end_s = float(start_s) + float(duration_s) if duration_s else (max(sample_times) if sample_times else None)
            if end_s is None:
                raise ValueError("No se puede determinar el intervalo de reproducción.")
            with st.spinner("Preparando el fragmento de vídeo del intervalo analizado…"):
                playback_path, playback_offset = prepare_playback_clip(ruta_gen, start_s, end_s)
            url_video = servir_video(playback_path)
            inj = ("<script>window.TRACKING_DATA = "
                   + json.dumps(datos_tracking, ensure_ascii=False,
                                separators=(",", ":")).replace("<", "\\u003c")
                   + "; window.TRACKING_FILE_NAME = "
                   + json.dumps(pista.name, ensure_ascii=False).replace("<", "\\u003c")
                   + ";")
            if url_video:
                inj += ("window.VIDEO_URL = " + json.dumps(url_video)
                        + "; window.VIDEO_OFFSET_S = " + json.dumps(playback_offset)
                        + "; window.VIDEO_NAME = "
                        + json.dumps(Path(ruta_gen).name, ensure_ascii=False).replace("<", "\\u003c")
                        + ";")
            inj += "</script>"
            html_pantalla = html_pantalla.replace(
                "<!-- TRACKING_DATA -->", inj, 1,
            )
            components.html(html_pantalla, height=1180, scrolling=True)
        except (OSError, TypeError, ValueError, RuntimeError) as error:
            st.error(f"No se pudo cargar el análisis: {error}")
    # Sólo este control discreto permite regresar al formulario.
    if st.button("Analizar otro vídeo", key="mv_video_new_analysis"):
        for clave in ("mv_video_ready_path", "mv_video_job",
                      "tracking_del_video", "video_analizado_path"):
            st.session_state.pop(clave, None)
        st.rerun()
