"""Interface Streamlit da Auditoria NBS."""

from __future__ import annotations

import importlib
import re
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

import backend_fiscal as motor
import backend_issqn as issqn
import manual_nfse as manual


# O Streamlit pode recarregar apenas este arquivo e manter uma versão anterior
# do backend em memória. Recarregamos o motor somente quando uma função exigida
# pela interface atual ainda não estiver disponível.
FUNCOES_MOTOR_OBRIGATORIAS = (
    "formatar_cnpj",
    "preparar_dados_empresa",
    "resumir_combinacoes",
    "filtrar_combinacoes",
    "gerar_combinacoes_codigo_servico",
    "diagnostico_setor",
)
if any(not hasattr(motor, nome) for nome in FUNCOES_MOTOR_OBRIGATORIAS):
    importlib.invalidate_caches()
    motor = importlib.reload(motor)


st.set_page_config(
    page_title="Auditoria NBS — Reforma Tributária",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      :root { --azul:#174a78; --azul-claro:#eaf2f8; --borda:#d9e3ec; --texto:#182433; }
      .block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1500px; }
      .app-header {
        background:#fff; border:1px solid var(--borda); border-left:6px solid var(--azul);
        padding:1.15rem 1.35rem; border-radius:14px; margin-bottom:1rem;
        box-shadow:0 4px 12px rgba(23,74,120,.07);
      }
      .app-header h1 { color:var(--azul); font-size:1.8rem; margin:0 0 .25rem 0; }
      .app-header p { color:#526273; margin:0; }
      .company-strip {
        background:#f7fafc; border:1px solid var(--borda); padding:.85rem 1rem;
        border-radius:12px; margin:.7rem 0 1rem 0;
      }
      .company-strip strong { color:var(--azul); }
      .empty-state {
        background:#f7fafc; border:1px dashed #aebdcc; border-radius:14px;
        padding:1.5rem; text-align:center; margin:1rem 0;
      }
      .detail-card { background:#f8fbfd; border:1px solid var(--borda); border-radius:12px; padding:1rem; }
      .service-panel-title {
        color:var(--azul); font-size:1.05rem; font-weight:700; padding:.15rem 0 .65rem 0;
        border-bottom:2px solid #b8cad9; margin-bottom:.35rem;
      }
      .service-field-label {
        color:#34495e; font-weight:650; padding-top:.55rem; text-align:right;
      }
      .required-mark { color:#b42318; margin-left:.2rem; }
      .tax-summary {
        background:#f8fbfd; border-left:4px solid var(--azul); padding:.8rem 1rem;
        border-radius:8px; margin:.45rem 0 .75rem 0;
      }
      .tax-summary strong { color:var(--azul); }
      .status-ok { color:#086444; background:#dff4e9; border-radius:999px; padding:.2rem .65rem; font-weight:650; }
      .status-review { color:#805500; background:#fff1c7; border-radius:999px; padding:.2rem .65rem; font-weight:650; }
      div[data-testid="stMetric"] { background:#f8fbfd; border:1px solid var(--borda); padding:12px; border-radius:12px; }
      div[data-testid="stMetricValue"] { font-variant-numeric:tabular-nums; }
      [data-testid="stSidebar"] { border-right:1px solid var(--borda); }
      .stDataFrame { font-variant-numeric:tabular-nums; }
      @media (max-width: 768px) {
        .service-field-label { text-align:left; padding-top:0; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


ETAPAS = [
    "1 · Empresa",
    "2 · Consulta individual",
    "3 · Simulação",
    "4 · Relatórios",
    "5 · Recomendações",
    "6 · ISSQN municipal",
]
ESTADO_INICIAL = {
    "empresa_selecionada": None,
    "relatorio_cnpj": None,
    "relatorio_manual": None,
    "servico_selecionado": None,
    "grupo_selecionado": None,
    "ultima_simulacao": None,
    "servico_simulado": None,
    "arquivos_relatorio": None,
    "arquivo_manual_nfse": None,
    "etapa_atual": ETAPAS[0],
    "etapa_pendente": None,
    "origem_classificacao": "CNPJ consultado",
    "modo_consulta_manual": "Consultar por CNAE",
    "setor_selecionado": "Tecnologia, informação e comunicação",
}
for chave, valor in ESTADO_INICIAL.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor

if st.session_state.etapa_pendente:
    st.session_state.etapa_atual = st.session_state.etapa_pendente
    st.session_state.etapa_pendente = None


def ir_para(etapa: str) -> None:
    st.session_state.etapa_pendente = etapa
    st.rerun()


def limpar_empresa() -> None:
    st.session_state.empresa_selecionada = None
    st.session_state.relatorio_cnpj = None
    st.session_state.servico_selecionado = None
    st.session_state.grupo_selecionado = None
    st.session_state.ultima_simulacao = None
    st.session_state.servico_simulado = None
    st.session_state.arquivos_relatorio = None
    st.session_state.arquivo_manual_nfse = None
    for chave in (
        "cnpj_servico_item",
        "cnpj_servico_cnae",
        "cnpj_servico_classificacao",
        "cnpj_servico_nbs",
    ):
        st.session_state.pop(chave, None)


def nome_empresa(dados: dict[str, Any]) -> str:
    return str(dados.get("razao_social") or dados.get("nome") or "Empresa consultada")


def moeda_br(valor: float) -> str:
    texto = f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def servico_a_partir_combinacao(linha: pd.Series | dict[str, Any]) -> dict[str, Any]:
    return {
        "Item LC 116": linha.get("Item LC 116", ""),
        "NBS": linha.get("NBS", ""),
        "DESCRIÇÃO NBS": linha.get("Descrição NBS", ""),
        "cClassTrib": linha.get("cClassTrib", ""),
        "nome cClassTrib": linha.get("Classificação Tributária", ""),
        "CNAE": linha.get("CNAE", ""),
        "Redução IBS (%)": linha.get("Redução IBS (%)", 0),
        "Redução CBS (%)": linha.get("Redução CBS (%)", 0),
        "Tipo de Alíquota": linha.get("Tipo de Alíquota", ""),
        "Fundamento legal": linha.get("Fundamento legal", motor.FONTE_LC_214),
    }


def garantir_opcao_valida(chave: str, opcoes: list[str]) -> None:
    """Mantém seletores dependentes consistentes entre reruns do Streamlit."""

    if opcoes and st.session_state.get(chave) not in opcoes:
        st.session_state[chave] = opcoes[0]


def painel_servico_cnpj(combinacoes: pd.DataFrame, df_regras: pd.DataFrame) -> None:
    """Exibe a seleção em cascata dos serviços encontrados para o CNPJ."""

    if combinacoes.empty:
        st.warning("Não há serviços conciliados para os CNAEs deste CNPJ.")
        return

    st.markdown('<div class="service-panel-title">Serviço prestado</div>', unsafe_allow_html=True)
    st.caption("Selecione os campos na ordem abaixo. Cada escolha restringe automaticamente a seguinte.")

    servicos = combinacoes[["Item LC 116", "Descrição LC 116"]].drop_duplicates()
    opcoes_servico = servicos["Item LC 116"].astype(str).tolist()
    rotulos_servico = {}
    for _, linha in servicos.iterrows():
        codigo = str(linha["Item LC 116"])
        descricao = str(linha["Descrição LC 116"])
        prefixo = f"{codigo} - "
        if descricao.startswith(prefixo):
            descricao = descricao[len(prefixo):]
        rotulos_servico[codigo] = f"{codigo} — {descricao}"
    garantir_opcao_valida("cnpj_servico_item", opcoes_servico)
    rotulo, campo = st.columns([.18, .82], vertical_alignment="center")
    rotulo.markdown('<div class="service-field-label">Serviço <span class="required-mark">*</span></div>', unsafe_allow_html=True)
    item = campo.selectbox(
        "Serviço prestado",
        opcoes_servico,
        key="cnpj_servico_item",
        format_func=lambda codigo: rotulos_servico.get(codigo, codigo),
        label_visibility="collapsed",
    )

    por_servico = combinacoes[combinacoes["Item LC 116"].astype(str).eq(str(item))]
    cnaes = por_servico[["CNAE", "Descrição CNAE"]].drop_duplicates()
    opcoes_cnae = cnaes["CNAE"].astype(str).tolist()
    rotulos_cnae = {
        str(linha["CNAE"]): f"{linha['CNAE']} — {linha['Descrição CNAE']}"
        for _, linha in cnaes.iterrows()
    }
    garantir_opcao_valida("cnpj_servico_cnae", opcoes_cnae)
    rotulo, campo = st.columns([.18, .82], vertical_alignment="center")
    rotulo.markdown('<div class="service-field-label">CNAE <span class="required-mark">*</span></div>', unsafe_allow_html=True)
    cnae = campo.selectbox(
        "CNAE da empresa",
        opcoes_cnae,
        key="cnpj_servico_cnae",
        format_func=lambda codigo: rotulos_cnae.get(codigo, codigo),
        label_visibility="collapsed",
    )

    por_cnae = por_servico[por_servico["CNAE"].astype(str).eq(str(cnae))]
    classificacoes = por_cnae[["cClassTrib", "Classificação Tributária"]].drop_duplicates()
    opcoes_classificacao = classificacoes["cClassTrib"].astype(str).tolist()
    rotulos_classificacao = {
        str(linha["cClassTrib"]): f"{linha['cClassTrib']} — {linha['Classificação Tributária']}"
        for _, linha in classificacoes.iterrows()
    }
    garantir_opcao_valida("cnpj_servico_classificacao", opcoes_classificacao)
    rotulo, campo, rotulo_anexo, campo_anexo = st.columns(
        [.18, .52, .12, .18], vertical_alignment="center"
    )
    rotulo.markdown('<div class="service-field-label">Cód. trib. reforma <span class="required-mark">*</span></div>', unsafe_allow_html=True)
    classificacao = campo.selectbox(
        "Classificação tributária IBS/CBS",
        opcoes_classificacao,
        key="cnpj_servico_classificacao",
        format_func=lambda codigo: rotulos_classificacao.get(codigo, codigo),
        label_visibility="collapsed",
    )
    regra = motor.obter_regra_tributaria(classificacao, df_regras)
    rotulo_anexo.markdown('<div class="service-field-label">Anexo</div>', unsafe_allow_html=True)
    campo_anexo.text_input(
        "Anexo legal",
        value=regra["numero_anexo"],
        disabled=True,
        label_visibility="collapsed",
    )

    por_classificacao = por_cnae[
        por_cnae["cClassTrib"].astype(str).eq(str(classificacao))
    ]
    nbs_df = por_classificacao[["NBS", "Descrição NBS"]].drop_duplicates()
    opcoes_nbs = nbs_df["NBS"].astype(str).tolist()
    rotulos_nbs = {
        str(linha["NBS"]): f"{linha['NBS']} — {linha['Descrição NBS']}"
        for _, linha in nbs_df.iterrows()
    }
    garantir_opcao_valida("cnpj_servico_nbs", opcoes_nbs)
    rotulo, campo = st.columns([.18, .82], vertical_alignment="center")
    rotulo.markdown('<div class="service-field-label">NBS <span class="required-mark">*</span></div>', unsafe_allow_html=True)
    nbs = campo.selectbox(
        "NBS candidata",
        opcoes_nbs,
        key="cnpj_servico_nbs",
        format_func=lambda codigo: rotulos_nbs.get(codigo, codigo),
        label_visibility="collapsed",
    )

    grupo = por_classificacao[por_classificacao["NBS"].astype(str).eq(str(nbs))].copy()
    if grupo.empty:
        st.warning("A combinação selecionada não está mais disponível. Revise os campos acima.")
        return
    primeiro = grupo.iloc[0]
    ibs_estimado = 17.7 * (1 - regra["reducao_ibs"] / 100)
    cbs_estimado = 8.8 * (1 - regra["reducao_cbs"] / 100)
    st.markdown(
        f"""
        <div class="tax-summary">
          <strong>Tributação da reforma</strong><br>
          Redução IBS: {regra['reducao_ibs']:.0f}% · Redução CBS: {regra['reducao_cbs']:.0f}% ·
          Tipo: {motor.escapar_html(regra['tipo_aliquota'])}<br>
          Referência estimada 2033 após redução: IBS {ibs_estimado:.2f}% + CBS {cbs_estimado:.2f}%
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Visualizar detalhes da combinação"):
        st.write(regra["descricao"])
        st.dataframe(
            grupo[["INDOP", "Detalhamento INDOP", "Status do vínculo"]].drop_duplicates(),
            width="stretch",
            hide_index=True,
            column_config={"Detalhamento INDOP": st.column_config.TextColumn(width="large")},
        )
        st.link_button("Abrir fundamento legal", regra["fundamento_legal"], width="stretch")

    simular, detalhar = st.columns(2)
    if simular.button("Usar esta seleção no simulador", type="primary", width="stretch"):
        st.session_state.servico_selecionado = servico_a_partir_combinacao(primeiro)
        st.session_state.grupo_selecionado = grupo
        st.session_state.ultima_simulacao = None
        st.session_state.servico_simulado = None
        ir_para(ETAPAS[2])
    if detalhar.button("Abrir consulta detalhada", width="stretch"):
        st.session_state.grupo_selecionado = grupo
        st.session_state.origem_classificacao = "CNPJ consultado"
        ir_para(ETAPAS[1])
    st.caption(motor.AVISO_CLASSIFICACAO)


try:
    df, df_indop, df_regras, df_cnae = motor.carregar_dados()
except (OSError, ValueError, KeyError) as erro:
    st.error(f"Não foi possível carregar as bases: {erro}")
    st.stop()

if df is None:
    st.error("Base principal não encontrada. Verifique os arquivos JSON do projeto.")
    st.stop()

integridade = motor.validar_integridade_dados(df, df_indop, df_regras, df_cnae)


with st.sidebar:
    st.markdown("### Auditoria NBS")
    st.caption(f"Base local · versão {integridade['versao_dados']}")
    st.link_button(
        "Voltar ao menu principal",
        "https://auditoria-fiscal.streamlit.app/",
        width="stretch",
    )
    st.divider()
    st.markdown("#### Contexto atual")
    if st.session_state.empresa_selecionada:
        empresa_sidebar = st.session_state.empresa_selecionada
        st.write(f"**{nome_empresa(empresa_sidebar)}**")
        st.caption(motor.formatar_cnpj(empresa_sidebar.get("cnpj")))
        if st.button("Trocar empresa", width="stretch"):
            limpar_empresa()
            ir_para(ETAPAS[0])
    else:
        st.info("Nenhuma empresa selecionada.")

    if st.session_state.servico_selecionado:
        servico_sidebar = st.session_state.servico_selecionado
        st.write(f"**NBS selecionada:** {servico_sidebar.get('NBS', '-')}")
        st.caption(f"Item LC 116 {servico_sidebar.get('Item LC 116', '-')}")

    with st.expander("Qualidade das bases"):
        st.write(f"NBS: **{integridade['registros_nbs']:,}**")
        st.write(f"Vínculos CNAE: **{integridade['registros_cnae']:,}**")
        st.write(f"Classificações sem regra: **{integridade['classificacoes_sem_regra']}**")
        st.write(f"INDOP sem auxiliar: **{integridade['indops_sem_tabela_auxiliar']}**")
        if integridade["itens_lc_sem_correspondencia"]:
            st.warning("Existem itens LC 116 não conciliados.")
        else:
            st.success("Itens LC 116 conciliados.")

    with st.expander("Fontes e responsabilidade"):
        st.caption(motor.AVISO_CLASSIFICACAO)
        st.link_button("Texto compilado da LC 214", motor.FONTE_LC_214, width="stretch")
        st.link_button("Painel oficial da NBS", motor.FONTE_NBS, width="stretch")


st.markdown(
    """
    <div class="app-header">
      <h1>Auditoria de serviços e NBS</h1>
      <p>Fluxo assistido para consultar a empresa, revisar candidatos, simular cenários e emitir relatórios.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

etapa = st.segmented_control(
    "Fluxo da análise",
    ETAPAS,
    key="etapa_atual",
    width="stretch",
    label_visibility="collapsed",
)

if st.session_state.empresa_selecionada:
    empresa_topo = st.session_state.empresa_selecionada
    st.markdown(
        f"""
        <div class="company-strip">
          <strong>{motor.escapar_html(nome_empresa(empresa_topo))}</strong><br>
          CNPJ {motor.escapar_html(motor.formatar_cnpj(empresa_topo.get('cnpj')))} ·
          Fonte: {motor.escapar_html(empresa_topo.get('fonte_dados') or 'não informada')}
        </div>
        """,
        unsafe_allow_html=True,
    )


if etapa == ETAPAS[0]:
    st.subheader("Empresa e atividades econômicas")
    st.caption("Comece pelo CNPJ para carregar os dados cadastrais e os CNAEs da empresa.")

    if not st.session_state.empresa_selecionada:
        formulario, orientacao = st.columns([1.15, 1], gap="large")
        with formulario:
            with st.container(border=True):
                st.markdown("#### Consultar CNPJ")
                with st.form("consulta_cnpj"):
                    cnpj_digitado = st.text_input(
                        "CNPJ",
                        max_chars=18,
                        placeholder="00.000.000/0000-00",
                    )
                    consentimento = st.checkbox(
                        "Estou ciente de que o CNPJ será enviado a uma base pública de consulta."
                    )
                    buscar = st.form_submit_button(
                        "Consultar empresa",
                        type="primary",
                        width="stretch",
                    )

                if buscar:
                    if not consentimento:
                        st.warning("Confirme a ciência sobre a consulta externa para continuar.")
                    elif not motor.validar_cnpj(cnpj_digitado):
                        st.error("CNPJ inválido. Confira os dígitos informados.")
                    else:
                        with st.spinner("Consultando a empresa e conciliando os CNAEs..."):
                            dados_empresa = motor.consultar_cnpj_api(cnpj_digitado)
                        if "erro" in dados_empresa:
                            st.error(dados_empresa["erro"])
                        else:
                            codigos = motor.extrair_cnaes_empresa(dados_empresa)
                            combinacoes = motor.gerar_combinacoes_cnae_nbs(
                                codigos, df_cnae, df, df_indop, df_regras
                            )
                            limpar_empresa()
                            st.session_state.empresa_selecionada = dados_empresa
                            st.session_state.relatorio_cnpj = combinacoes
                            st.session_state.origem_classificacao = "CNPJ consultado"
                            st.session_state.etapa_pendente = ETAPAS[1]
                            st.rerun()
        with orientacao:
            st.markdown("#### O que acontecerá")
            st.write("1. Conferência dos dados cadastrais.")
            st.write("2. Identificação dos CNAEs principal e secundários.")
            st.write("3. Cruzamento com LC 116, NBS, cClassTrib e INDOP.")
            st.write("4. Seleção de um candidato para simulação e relatório.")
            st.info("Sem CNPJ? Utilize uma das duas opções na etapa Consulta individual.")
            if st.button("Ir para consulta manual", width="stretch"):
                st.session_state.origem_classificacao = "Consulta manual"
                ir_para(ETAPAS[1])
    else:
        empresa = st.session_state.empresa_selecionada
        codigos = motor.extrair_cnaes_empresa(empresa)
        combinacoes = st.session_state.relatorio_cnpj
        combinacoes = combinacoes if isinstance(combinacoes, pd.DataFrame) else pd.DataFrame()
        ficha = motor.preparar_dados_empresa(empresa)

        metricas = st.columns(4)
        metricas[0].metric("CNAEs", len(codigos))
        metricas[1].metric("Itens LC 116", combinacoes["Item LC 116"].nunique() if not combinacoes.empty else 0)
        metricas[2].metric("NBS candidatas", combinacoes["NBS"].replace("Não localizada", pd.NA).nunique() if not combinacoes.empty else 0)
        metricas[3].metric("Opções INDOP", combinacoes["INDOP"].replace("", pd.NA).nunique() if not combinacoes.empty else 0)

        with st.container(border=True):
            painel_servico_cnpj(combinacoes, df_regras)

        identificacao, atividades = st.columns([1, 1.2], gap="large")
        with identificacao:
            st.markdown("#### Dados cadastrais")
            st.dataframe(
                ficha,
                width="stretch",
                hide_index=True,
                height=410,
                column_config={
                    "Seção": st.column_config.TextColumn(width="medium"),
                    "Campo": st.column_config.TextColumn(width="medium"),
                    "Informação": st.column_config.TextColumn(width="large"),
                },
            )
        with atividades:
            st.markdown("#### Atividades identificadas")
            atividades_df = (
                df_cnae[df_cnae["cnae_numeros"].isin(codigos)][
                    ["cnae", "descricao_cnae"]
                ]
                .drop_duplicates()
                .rename(columns={"cnae": "CNAE", "descricao_cnae": "Descrição"})
            )
            if atividades_df.empty:
                st.warning("Os CNAEs informados pela fonte não constam na base local.")
            else:
                st.dataframe(atividades_df, width="stretch", hide_index=True, height=410)

        acao_1, acao_2 = st.columns([2, 1])
        if acao_1.button("Continuar para consulta individual", type="primary", width="stretch"):
            st.session_state.origem_classificacao = "CNPJ consultado"
            ir_para(ETAPAS[1])
        if acao_2.button("Consultar outro CNPJ", width="stretch"):
            limpar_empresa()
            st.rerun()


elif etapa == ETAPAS[1]:
    st.subheader("Consulta individual de serviços")
    st.caption("Escolha a entrada: o CNAE mostra os códigos de serviço; o código de serviço mostra os CNAEs relacionados.")

    origens = ["Consulta manual"]
    if st.session_state.empresa_selecionada:
        origens.insert(0, "CNPJ consultado")
    if st.session_state.origem_classificacao not in origens:
        st.session_state.origem_classificacao = origens[0]
    origem = st.segmented_control(
        "Origem da análise",
        origens,
        key="origem_classificacao",
        width="stretch",
    )

    combinacoes_ativas = pd.DataFrame()
    if origem == "CNPJ consultado":
        relatorio = st.session_state.relatorio_cnpj
        combinacoes_ativas = relatorio if isinstance(relatorio, pd.DataFrame) else pd.DataFrame()
        if combinacoes_ativas.empty:
            st.markdown('<div class="empty-state"><strong>Nenhuma combinação encontrada.</strong><br>Revise os CNAEs ou utilize a consulta manual.</div>', unsafe_allow_html=True)
    else:
        with st.container(border=True):
            st.markdown("#### Como deseja consultar?")
            modo_consulta = st.segmented_control(
                "Tipo de consulta",
                ["Consultar por CNAE", "Consultar por código de serviço"],
                key="modo_consulta_manual",
                width="stretch",
                label_visibility="collapsed",
            )
            if modo_consulta == "Consultar por CNAE":
                st.caption("Informe um CNAE ou uma atividade para receber os códigos LC 116, NBS e tributos da reforma.")
                termo_manual = st.text_input(
                    "CNAE ou atividade",
                    placeholder="Ex.: 6201-5/01 ou desenvolvimento de software",
                    key="termo_manual_cnae",
                )
                resultado_manual = motor.buscar_cnae(df_cnae, termo_manual) if termo_manual else pd.DataFrame()
                if termo_manual and resultado_manual.empty:
                    st.warning("Nenhum CNAE correspondente foi localizado.")
                elif not resultado_manual.empty:
                    st.dataframe(
                        resultado_manual[["cnae", "descricao_cnae", "item_lista_servico"]].rename(
                            columns={"cnae": "CNAE", "descricao_cnae": "Atividade", "item_lista_servico": "Código LC 116"}
                        ),
                        width="stretch",
                        hide_index=True,
                        height=250,
                    )
                    opcoes = sorted(resultado_manual["cnae_numeros"].unique())
                    selecionados = st.multiselect(
                        "CNAEs para analisar",
                        opcoes,
                        default=opcoes[: min(10, len(opcoes))],
                        format_func=motor.formatar_cnae,
                    )
                    if st.button("Consultar CNAEs selecionados", type="primary", width="stretch"):
                        st.session_state.relatorio_manual = motor.gerar_combinacoes_cnae_nbs(
                            selecionados, df_cnae, df, df_indop, df_regras
                        )
                        st.session_state.grupo_selecionado = None
                        st.session_state.arquivos_relatorio = None
                        st.rerun()
            else:
                st.caption("Informe o item da LC 116 para receber os CNAEs, NBS e tributos da reforma relacionados.")
                termo_servico = st.text_input(
                    "Código ou descrição do serviço",
                    placeholder="Ex.: 1.01 ou desenvolvimento de sistemas",
                    key="termo_manual_servico",
                )
                resultado_servico = (
                    motor.buscar_codigos_servico(df_cnae, termo_servico)
                    if termo_servico
                    else pd.DataFrame()
                )
                if termo_servico and resultado_servico.empty:
                    st.warning("Nenhum código de serviço correspondente foi localizado.")
                elif not resultado_servico.empty:
                    exibicao_servico = resultado_servico.rename(
                        columns={"item_lista_servico": "Código LC 116", "descricao_item": "Descrição"}
                    )
                    st.dataframe(exibicao_servico, width="stretch", hide_index=True, height=250)
                    descricoes = dict(
                        zip(resultado_servico["item_lista_servico"], resultado_servico["descricao_item"])
                    )
                    codigos = resultado_servico["item_lista_servico"].tolist()
                    selecionados = st.multiselect(
                        "Códigos para analisar",
                        codigos,
                        default=codigos[: min(10, len(codigos))],
                        format_func=lambda codigo: f"{codigo} — {descricoes.get(codigo, '')}",
                    )
                    if st.button("Consultar códigos selecionados", type="primary", width="stretch"):
                        st.session_state.relatorio_manual = motor.gerar_combinacoes_codigo_servico(
                            selecionados, df_cnae, df, df_indop, df_regras
                        )
                        st.session_state.grupo_selecionado = None
                        st.session_state.arquivos_relatorio = None
                        st.rerun()
        relatorio = st.session_state.relatorio_manual
        combinacoes_ativas = relatorio if isinstance(relatorio, pd.DataFrame) else pd.DataFrame()

    if not combinacoes_ativas.empty:
        st.markdown("#### Resultados")
        filtro_1, filtro_2, filtro_3 = st.columns([1.3, 1, .75])
        termo_resultado = filtro_1.text_input(
            "Filtrar resultados",
            placeholder="CNAE, NBS, descrição ou INDOP",
            key=f"filtro_{origem}",
        )
        regras_opcoes = sorted(
            combinacoes_ativas["Classificação Tributária"].dropna().astype(str).unique()
        )
        regras_filtro = filtro_2.multiselect(
            "Classificação tributária",
            regras_opcoes,
            key=f"regras_{origem}",
        )
        visao = filtro_3.radio(
            "Visualização",
            ["Resumida", "Detalhada"],
            horizontal=True,
            key=f"visao_{origem}",
        )
        filtradas = motor.filtrar_combinacoes(
            combinacoes_ativas, termo_resultado, regras_filtro
        )
        resumo = motor.resumir_combinacoes(filtradas)

        indicadores = st.columns(4)
        indicadores[0].metric("Combinações", len(resumo))
        indicadores[1].metric("CNAEs", resumo["CNAE"].nunique())
        indicadores[2].metric("NBS", resumo["NBS"].replace("Não localizada", pd.NA).nunique())
        indicadores[3].metric("Opções INDOP", filtradas["INDOP"].replace("", pd.NA).nunique())

        if visao == "Resumida":
            tabela = resumo[
                [
                    "CNAE",
                    "Descrição CNAE",
                    "Item LC 116",
                    "NBS",
                    "Descrição NBS",
                    "cClassTrib",
                    "Redução IBS (%)",
                    "Redução CBS (%)",
                    "Tipo de Alíquota",
                    "Quantidade INDOP",
                    "Status do vínculo",
                ]
            ]
        else:
            tabela = filtradas[
                [
                    "CNAE",
                    "Descrição CNAE",
                    "Item LC 116",
                    "NBS",
                    "Descrição NBS",
                    "cClassTrib",
                    "Redução IBS (%)",
                    "Redução CBS (%)",
                    "Tipo de Alíquota",
                    "INDOP",
                    "Status do vínculo",
                ]
            ]

        evento = st.dataframe(
            tabela,
            width="stretch",
            hide_index=True,
            height=440,
            selection_mode="single-row",
            on_select="rerun",
            column_config={
                "Descrição NBS": st.column_config.TextColumn(width="large"),
                "Descrição CNAE": st.column_config.TextColumn("Atividade CNAE", width="large"),
                "Redução IBS (%)": st.column_config.NumberColumn("Red. IBS", format="%.0f%%", width="small"),
                "Redução CBS (%)": st.column_config.NumberColumn("Red. CBS", format="%.0f%%", width="small"),
                "Quantidade INDOP": st.column_config.NumberColumn("Opções", width="small"),
                "Status do vínculo": st.column_config.TextColumn("Status", width="medium"),
            },
        )

        if evento.selection.rows:
            linha_selecionada = (
                resumo.iloc[evento.selection.rows[0]]
                if visao == "Resumida"
                else filtradas.iloc[evento.selection.rows[0]]
            )
            chaves = ["CNAE", "Item LC 116", "NBS", "cClassTrib"]
            mascara = pd.Series(True, index=filtradas.index)
            for chave in chaves:
                mascara &= filtradas[chave].astype(str).eq(str(linha_selecionada[chave]))
            grupo = filtradas[mascara].copy()
            st.session_state.grupo_selecionado = grupo

        grupo = st.session_state.grupo_selecionado
        if isinstance(grupo, pd.DataFrame) and not grupo.empty:
            primeiro = grupo.iloc[0]
            st.markdown("#### Detalhes do candidato selecionado")
            detalhe_1, detalhe_2 = st.columns([1.25, 1], gap="large")
            with detalhe_1:
                with st.container(border=True):
                    st.write(f"**CNAE:** {primeiro['CNAE']} — {primeiro['Descrição CNAE']}")
                    st.write(f"**NBS:** {primeiro['NBS']}")
                    st.write(f"**Descrição:** {primeiro['Descrição NBS']}")
                    st.write(f"**Item LC 116:** {primeiro['Item LC 116']}")
                    st.write(f"**cClassTrib:** {primeiro['cClassTrib']}")
                    st.write(f"**Regra:** {primeiro['Classificação Tributária']}")
            with detalhe_2:
                regra = motor.obter_regra_tributaria(primeiro["cClassTrib"], df_regras)
                reducao_1, reducao_2 = st.columns(2)
                reducao_1.metric("Redução IBS", f"{regra['reducao_ibs']:.0f}%")
                reducao_2.metric("Redução CBS", f"{regra['reducao_cbs']:.0f}%")
                ibs_estimado = 17.7 * (1 - regra["reducao_ibs"] / 100)
                cbs_estimado = 8.8 * (1 - regra["reducao_cbs"] / 100)
                st.caption(
                    f"Referência estimada de 2033 após redução: IBS {ibs_estimado:.2f}% + CBS {cbs_estimado:.2f}%. "
                    "As alíquotas de referência são editáveis no simulador."
                )
                st.write(f"**Tipo de alíquota:** {regra['tipo_aliquota']}")
                st.link_button("Abrir fundamento legal", regra["fundamento_legal"], width="stretch")
                st.dataframe(
                    grupo[["INDOP", "Detalhamento INDOP"]].drop_duplicates(),
                    width="stretch",
                    hide_index=True,
                    height=230,
                    column_config={"Detalhamento INDOP": st.column_config.TextColumn(width="large")},
                )
            acao_simular, acao_setor = st.columns(2)
            if acao_simular.button("Usar esta NBS no simulador", type="primary", width="stretch"):
                novo_servico = servico_a_partir_combinacao(primeiro)
                if st.session_state.servico_selecionado != novo_servico:
                    st.session_state.ultima_simulacao = None
                    st.session_state.servico_simulado = None
                st.session_state.servico_selecionado = novo_servico
                ir_para(ETAPAS[2])
            if acao_setor.button("Ver recomendações do setor", width="stretch"):
                st.session_state.setor_selecionado = motor.identificar_setor_cnae(primeiro["CNAE"])
                ir_para(ETAPAS[4])
        else:
            st.info("Selecione uma linha da tabela para abrir os detalhes e continuar.")
    elif origem == "Consulta manual":
        st.markdown('<div class="empty-state"><strong>Inicie uma consulta individual.</strong><br>Escolha CNAE ou código de serviço acima e selecione os itens que deseja analisar.</div>', unsafe_allow_html=True)


elif etapa == ETAPAS[2]:
    st.subheader("Simulação tributária")
    servico = st.session_state.servico_selecionado
    if not servico:
        st.markdown('<div class="empty-state"><strong>Nenhuma NBS foi selecionada.</strong><br>Escolha um candidato na Consulta individual antes de simular.</div>', unsafe_allow_html=True)
        if st.button("Ir para consulta", type="primary"):
            ir_para(ETAPAS[1])
    else:
        with st.container(border=True):
            st.write(f"**NBS {servico['NBS']} · Item LC 116 {servico['Item LC 116']}**")
            st.write(servico["DESCRIÇÃO NBS"])
            st.caption(f"cClassTrib {servico['cClassTrib']} · {servico.get('nome cClassTrib', '')}")
            regra_servico = motor.obter_regra_tributaria(servico["cClassTrib"], df_regras)
            resumo_reducao = st.columns(3)
            resumo_reducao[0].metric("Redução IBS", f"{regra_servico['reducao_ibs']:.0f}%")
            resumo_reducao[1].metric("Redução CBS", f"{regra_servico['reducao_cbs']:.0f}%")
            resumo_reducao[2].metric("Tipo", regra_servico["tipo_aliquota"])
            st.link_button("Ver fundamento da redução/regra", regra_servico["fundamento_legal"])

        formulario, resultado_area = st.columns([1, 1.15], gap="large")
        with formulario:
            st.markdown("#### Parâmetros")
            cenario = st.selectbox(
                "Cenário de alíquotas",
                ["2026 — ano de teste", "2033 — referência estimada", "Personalizado"],
            )
            if cenario.startswith("2026"):
                ano_padrao, ibs_padrao, cbs_padrao = 2026, 0.1, 0.9
            elif cenario.startswith("2033"):
                ano_padrao, ibs_padrao, cbs_padrao = 2033, 17.7, 8.8
            else:
                ano_padrao, ibs_padrao, cbs_padrao = 2026, 0.1, 0.9

            with st.form("form_simulacao"):
                valor = st.number_input("Valor do serviço (R$)", min_value=0.0, value=10000.0, step=500.0)
                regime = st.selectbox(
                    "Regime/contexto",
                    ["Não informado", "Lucro presumido", "Lucro real", "Simples Nacional", "Outro"],
                )
                ano = st.number_input(
                    "Ano do cenário",
                    min_value=2026,
                    max_value=2033,
                    value=ano_padrao,
                    disabled=cenario != "Personalizado",
                )
                atual_1, atual_2, atual_3 = st.columns(3)
                iss = atual_1.number_input("ISS (%)", 0.0, 100.0, 5.0, 0.1)
                pis = atual_2.number_input("PIS (%)", 0.0, 100.0, 0.65, 0.05)
                cofins = atual_3.number_input("COFINS (%)", 0.0, 100.0, 3.0, 0.1)
                novo_1, novo_2 = st.columns(2)
                ibs = novo_1.number_input(
                    "IBS de referência (%)",
                    0.0,
                    100.0,
                    ibs_padrao,
                    0.1,
                    disabled=cenario != "Personalizado",
                )
                cbs = novo_2.number_input(
                    "CBS de referência (%)",
                    0.0,
                    100.0,
                    cbs_padrao,
                    0.1,
                    disabled=cenario != "Personalizado",
                )
                cred_1, cred_2 = st.columns(2)
                credito_atual = cred_1.number_input("Créditos atuais (%)", 0.0, 100.0, 0.0, 1.0)
                credito_novo = cred_2.number_input("Créditos IBS/CBS (%)", 0.0, 100.0, 0.0, 1.0)
                calcular = st.form_submit_button("Calcular cenário", type="primary", width="stretch")

            if calcular:
                try:
                    st.session_state.ultima_simulacao = motor.calcular_comparativo(
                        valor,
                        iss,
                        pis,
                        cofins,
                        ibs,
                        cbs,
                        servico["cClassTrib"],
                        df_regras,
                        ano=int(ano),
                        regime=regime,
                        credito_atual=credito_atual,
                        credito_novo=credito_novo,
                    )
                    st.session_state.servico_simulado = servico
                    st.session_state.arquivos_relatorio = None
                except motor.ValidacaoFiscalError as erro:
                    st.error(str(erro))

        with resultado_area:
            st.markdown("#### Resultado")
            resultado = st.session_state.ultima_simulacao
            if not resultado or st.session_state.servico_simulado != servico:
                st.markdown('<div class="empty-state"><strong>Informe os parâmetros e calcule o cenário.</strong><br>O comparativo aparecerá nesta área.</div>', unsafe_allow_html=True)
            else:
                metrica_1, metrica_2, metrica_3 = st.columns(3)
                metrica_1.metric("Sistema atual", moeda_br(resultado["valor_atual"]), f"{resultado['aliq_total_atual']:.2f}%")
                metrica_2.metric("IBS/CBS", moeda_br(resultado["valor_novo"]), f"{resultado['aliq_total_nova']:.2f}%")
                metrica_3.metric("Diferença", moeda_br(resultado["diferenca"]))

                grafico = pd.DataFrame(
                    {
                        "Cenário": ["Sistema atual", "IBS/CBS"],
                        "Valor líquido": [resultado["valor_atual"], resultado["valor_novo"]],
                    }
                ).set_index("Cenário")
                st.bar_chart(grafico, color="#174a78")
                detalhamento = pd.DataFrame(
                    [
                        ["Sistema atual", resultado["aliq_total_atual"], resultado["valor_credito_atual"], resultado["valor_atual"]],
                        ["IBS/CBS", resultado["aliq_total_nova"], resultado["valor_credito_novo"], resultado["valor_novo"]],
                    ],
                    columns=["Cenário", "Alíquota (%)", "Créditos (R$)", "Valor líquido (R$)"],
                )
                st.dataframe(detalhamento, width="stretch", hide_index=True)
                if resultado["reducao_ibs"] or resultado["reducao_cbs"]:
                    st.success(
                        f"Redução aplicada no cálculo: IBS {resultado['reducao_ibs']:.0f}% e "
                        f"CBS {resultado['reducao_cbs']:.0f}%. Alíquotas efetivas: "
                        f"IBS {resultado['ibs_efetivo']:.2f}% + CBS {resultado['cbs_efetivo']:.2f}%."
                    )
                else:
                    st.info("A cClassTrib selecionada não possui redução percentual na base atual.")
                st.warning(resultado["observacao"], icon="⚠️")
                pdf_simulacao = motor.gerar_relatorio_pdf(
                    st.session_state.empresa_selecionada,
                    resultado,
                    servico,
                )
                st.download_button(
                    "Baixar esta simulação em PDF",
                    pdf_simulacao,
                    "simulacao_tributaria.pdf",
                    "application/pdf",
                    width="stretch",
                )
                if st.button("Continuar para relatórios", type="primary", width="stretch"):
                    ir_para(ETAPAS[3])


elif etapa == ETAPAS[3]:
    st.subheader("Central de relatórios")
    st.caption("Escolha o conteúdo, confira a prévia e prepare os arquivos somente quando precisar.")

    fontes_relatorio: dict[str, pd.DataFrame] = {}
    if isinstance(st.session_state.relatorio_cnpj, pd.DataFrame) and not st.session_state.relatorio_cnpj.empty:
        fontes_relatorio["Empresa consultada"] = st.session_state.relatorio_cnpj
    if isinstance(st.session_state.relatorio_manual, pd.DataFrame) and not st.session_state.relatorio_manual.empty:
        fontes_relatorio["Consulta manual"] = st.session_state.relatorio_manual

    if not fontes_relatorio:
        st.markdown('<div class="empty-state"><strong>Não há resultados para exportar.</strong><br>Realize uma consulta por CNPJ, CNAE ou código de serviço.</div>', unsafe_allow_html=True)
        if st.button("Ir para consulta", type="primary"):
            ir_para(ETAPAS[1])
    else:
        configuracao, previa = st.columns([.85, 1.35], gap="large")
        with configuracao:
            with st.container(border=True):
                st.markdown("#### Configuração")
                fonte_nome = st.selectbox("Origem dos dados", list(fontes_relatorio))
                modo = st.segmented_control(
                    "Nível de detalhe",
                    ["Resumido", "Completo"],
                    default="Resumido",
                    width="stretch",
                )
                base_relatorio = fontes_relatorio[fonte_nome]
                cnaes_disponiveis = sorted(base_relatorio["CNAE"].dropna().unique())
                cnaes_relatorio = st.multiselect(
                    "CNAEs incluídos",
                    cnaes_disponiveis,
                    default=cnaes_disponiveis,
                )
                incluir_empresa = st.checkbox(
                    "Incluir ficha cadastral da empresa",
                    value=fonte_nome == "Empresa consultada",
                    disabled=fonte_nome != "Empresa consultada",
                )
                if not cnaes_relatorio:
                    st.warning("Selecione pelo menos um CNAE.")

        base_filtrada = base_relatorio[base_relatorio["CNAE"].isin(cnaes_relatorio)].copy()
        dados_exportacao = (
            motor.resumir_combinacoes(base_filtrada) if modo == "Resumido" else base_filtrada
        )
        with previa:
            st.markdown("#### Prévia")
            resumo_cols = st.columns(3)
            resumo_cols[0].metric("Linhas", len(dados_exportacao))
            resumo_cols[1].metric("CNAEs", dados_exportacao["CNAE"].nunique() if not dados_exportacao.empty else 0)
            resumo_cols[2].metric("NBS", dados_exportacao["NBS"].replace("Não localizada", pd.NA).nunique() if not dados_exportacao.empty else 0)
            st.dataframe(dados_exportacao.head(200), width="stretch", hide_index=True, height=390)
            if len(dados_exportacao) > 200:
                st.caption("A prévia mostra 200 linhas; o arquivo conterá todas as linhas selecionadas.")

        assinatura = (
            fonte_nome,
            modo,
            tuple(cnaes_relatorio),
            incluir_empresa,
            len(dados_exportacao),
        )
        preparar = st.button(
            "Preparar Excel e PDF",
            type="primary",
            width="stretch",
            disabled=dados_exportacao.empty,
        )
        if preparar:
            empresa_exportacao = (
                st.session_state.empresa_selecionada
                if incluir_empresa and st.session_state.empresa_selecionada
                else {"nome": fonte_nome, "fonte_dados": "Base local"}
            )
            with st.spinner("Formatando os arquivos..."):
                excel = motor.gerar_excel_completo(
                    empresa_exportacao,
                    dados_exportacao,
                    incluir_dados_empresa=incluir_empresa,
                )
                pdf = motor.gerar_pdf_paisagem(empresa_exportacao, dados_exportacao)
            st.session_state.arquivos_relatorio = {
                "assinatura": assinatura,
                "excel": excel,
                "pdf": pdf,
                "nome": re.sub(r"\D", "", str(empresa_exportacao.get("cnpj", ""))) or "consulta",
            }

        arquivos = st.session_state.arquivos_relatorio
        if arquivos and arquivos.get("assinatura") == assinatura:
            st.success("Arquivos preparados com sucesso.")
            botao_excel, botao_pdf = st.columns(2)
            botao_excel.download_button(
                "Baixar Excel formatado",
                arquivos["excel"],
                f"candidatos_nbs_{arquivos['nome']}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
            botao_pdf.download_button(
                "Baixar relatório PDF",
                arquivos["pdf"],
                f"candidatos_nbs_{arquivos['nome']}.pdf",
                "application/pdf",
                width="stretch",
            )
        elif arquivos:
            st.info("A configuração mudou. Clique em “Preparar Excel e PDF” para atualizar os arquivos.")


elif etapa == ETAPAS[4]:
    st.subheader("Recomendações por setor de serviço")
    st.caption(
        "Use este roteiro para priorizar a revisão. As recomendações indicam documentos e requisitos a conferir; "
        "não concedem benefício automaticamente."
    )

    setores = list(motor.SETORES_SERVICO)
    if st.session_state.setor_selecionado not in setores:
        st.session_state.setor_selecionado = setores[0]
    setor = st.selectbox(
        "Setor de serviço",
        setores,
        key="setor_selecionado",
    )
    diagnostico = motor.diagnostico_setor(setor, df_cnae, df, df_regras)

    st.info(f"**Foco deste setor:** {diagnostico['foco']}.")
    metricas_setor = st.columns(4)
    metricas_setor[0].metric("CNAEs na base", diagnostico["cnaes"])
    metricas_setor[1].metric("Itens LC 116", diagnostico["itens_lc"])
    metricas_setor[2].metric("NBS relacionadas", diagnostico["nbs"])
    metricas_setor[3].metric("Candidatos com redução", len(diagnostico["candidatos_reducao"]))

    roteiro, oportunidades = st.columns([1, 1.25], gap="large")
    with roteiro:
        with st.container(border=True):
            st.markdown("#### Roteiro recomendado")
            for indice, recomendacao in enumerate(diagnostico["recomendacoes"], start=1):
                st.write(f"{indice}. {recomendacao}")
            st.divider()
            st.markdown("**Para todas as atividades**")
            st.write("1. Confirmar a natureza real da prestação e o contrato.")
            st.write("2. Validar item LC 116, NBS, cClassTrib e INDOP em conjunto.")
            st.write("3. Guardar a evidência do requisito que sustenta eventual redução.")
            st.write("4. Revisar cadastro, documento fiscal, créditos e transição por ano.")
    with oportunidades:
        st.markdown("#### Possíveis reduções na base")
        candidatos = diagnostico["candidatos_reducao"].copy()
        if candidatos.empty:
            st.info("Não foram localizados candidatos com redução para este recorte setorial.")
        else:
            regras_setor = {
                codigo: motor.obter_regra_tributaria(codigo, df_regras)
                for codigo in candidatos["cClassTrib"].unique()
            }
            candidatos["Redução IBS (%)"] = candidatos["cClassTrib"].map(
                lambda codigo: regras_setor[codigo]["reducao_ibs"]
            )
            candidatos["Redução CBS (%)"] = candidatos["cClassTrib"].map(
                lambda codigo: regras_setor[codigo]["reducao_cbs"]
            )
            st.warning(
                "Candidato não significa direito confirmado: valide NBS, operação, anexos e requisitos do fundamento legal.",
                icon="⚠️",
            )
            st.dataframe(
                candidatos.rename(
                    columns={"DESCRIÇÃO NBS": "Descrição NBS", "nome cClassTrib": "Regra tributária"}
                ),
                width="stretch",
                hide_index=True,
                height=430,
                column_config={
                    "Descrição NBS": st.column_config.TextColumn(width="large"),
                    "Regra tributária": st.column_config.TextColumn(width="large"),
                    "Redução IBS (%)": st.column_config.NumberColumn("Red. IBS", format="%.0f%%"),
                    "Redução CBS (%)": st.column_config.NumberColumn("Red. CBS", format="%.0f%%"),
                },
            )
            codigos_regras = sorted(candidatos["cClassTrib"].unique())
            codigo_regra = st.selectbox("Abrir fundamento de uma cClassTrib", codigos_regras)
            regra_setor = regras_setor[codigo_regra]
            st.write(regra_setor["descricao"])
            st.link_button("Consultar texto legal", regra_setor["fundamento_legal"], width="stretch")

    st.link_button("Abrir LC 214/2025 — texto compilado", motor.FONTE_LC_214, width="stretch")


elif etapa == ETAPAS[5]:
    st.subheader("Alíquotas municipais de ISSQN")
    st.caption(
        "Consulte a alíquota cadastrada no Sistema Nacional da NFS-e pela localidade de incidência, "
        "Código de Tributação Nacional e data de competência."
    )

    try:
        resumo_issqn = issqn.resumo_base()
    except issqn.BaseISSQNError as erro:
        st.warning(str(erro))
        st.code("python backend_issqn.py", language="powershell")
        st.link_button(
            "Abrir fonte oficial das alíquotas",
            issqn.FONTE_ALIQUOTAS,
            width="stretch",
        )
    else:
        cobertura = st.columns(4)
        cobertura[0].metric("Registros", f"{int(resumo_issqn['registros']):,}".replace(",", "."))
        cobertura[1].metric("Municípios com registros", f"{int(resumo_issqn['municipios']):,}".replace(",", "."))
        cobertura[2].metric("Códigos nacionais", resumo_issqn["servicos"])
        cobertura[3].metric(
            "Alíquotas não informadas",
            f"{int(resumo_issqn['aliquotas_ausentes']):,}".replace(",", "."),
        )
        if int(resumo_issqn.get("intervalos_invalidos", 0)):
            st.warning(
                f"A fonte contém {int(resumo_issqn['intervalos_invalidos']):,} intervalos com fim anterior ao início. "
                "Eles foram preservados para auditoria e não entram em consultas vigentes."
            )

        empresa_issqn = st.session_state.empresa_selecionada or {}
        local_empresa = issqn.extrair_localidade_empresa(empresa_issqn)
        item_selecionado = str(
            (st.session_state.servico_selecionado or {}).get("Item LC 116", "")
        )

        with st.container(border=True):
            st.markdown("#### Parâmetros da consulta")
            if empresa_issqn:
                st.info(
                    f"Empresa: **{nome_empresa(empresa_issqn)}** · "
                    f"Localidade cadastral: **{local_empresa['municipio'] or 'não identificada'}/"
                    f"{local_empresa['uf'] or '--'}**"
                )

            local_1, local_2, local_3 = st.columns([1, 2, 1.1])
            codigo_ibge_issqn = local_1.text_input(
                "Código IBGE",
                value=local_empresa["codigo_ibge"],
                max_chars=7,
                help="Quando disponível, é a forma mais segura de identificar o município.",
            )
            municipio_issqn = local_2.text_input(
                "Município",
                value=local_empresa["municipio"],
            )
            uf_issqn = local_3.text_input(
                "UF",
                value=local_empresa["uf"],
                max_chars=2,
            )

            filtro_1, filtro_2, filtro_3 = st.columns([1.1, 1.5, 1.1])
            modo_issqn = filtro_1.selectbox(
                "Tipo de código",
                ["Item LC 116", "Código de Tributação Nacional"],
            )
            codigo_consulta_issqn = filtro_2.text_input(
                "Código para consulta",
                value=item_selecionado if modo_issqn == "Item LC 116" else "",
                placeholder="1.01" if modo_issqn == "Item LC 116" else "01.01.01.000",
            )
            data_issqn = filtro_3.date_input(
                "Data de competência",
                value=date.today(),
                format="DD/MM/YYYY",
            )

        try:
            consulta_issqn = issqn.consultar_aliquotas(
                codigo_ibge=codigo_ibge_issqn,
                municipio=municipio_issqn,
                uf=uf_issqn,
                item_lc116=codigo_consulta_issqn if modo_issqn == "Item LC 116" else "",
                codigo_servico=(
                    codigo_consulta_issqn
                    if modo_issqn == "Código de Tributação Nacional"
                    else ""
                ),
                data_referencia=data_issqn,
            )
        except issqn.BaseISSQNError as erro:
            st.error(str(erro))
        else:
            local_encontrado = consulta_issqn["municipio"]
            registros_issqn = consulta_issqn["registros"]
            if not local_encontrado:
                st.warning(
                    "Município não localizado na base. Confira o código IBGE ou informe município e UF."
                )
            elif not registros_issqn:
                st.warning(
                    "Não há alíquota vigente para os parâmetros informados. Isso não equivale a alíquota zero."
                )
            else:
                st.markdown(
                    f"#### {local_encontrado['nome']}/{local_encontrado['uf']} · "
                    f"competência {data_issqn.strftime('%d/%m/%Y')}"
                )
                tabela_issqn = pd.DataFrame(registros_issqn).rename(
                    columns={
                        "codigo_servico": "Código de Tributação Nacional",
                        "incidencia": "Código de incidência",
                        "aliquota": "Alíquota ISSQN (%)",
                        "dt_ini": "Início da vigência",
                        "dt_fim": "Fim da vigência",
                    }
                )
                tabela_issqn.insert(
                    1,
                    "Descrição oficial",
                    tabela_issqn["Código de Tributação Nacional"].map(
                        manual.descricao_codigo_servico
                    ),
                )
                st.dataframe(
                    tabela_issqn,
                    width="stretch",
                    hide_index=True,
                    height=min(520, 38 + len(tabela_issqn) * 35),
                    column_config={
                        "Código de Tributação Nacional": st.column_config.TextColumn(width="medium"),
                        "Descrição oficial": st.column_config.TextColumn(width="large"),
                        "Código de incidência": st.column_config.TextColumn(width="medium"),
                        "Alíquota ISSQN (%)": st.column_config.NumberColumn(format="%.2f%%"),
                        "Início da vigência": st.column_config.DateColumn(format="DD/MM/YYYY"),
                        "Fim da vigência": st.column_config.DateColumn(format="DD/MM/YYYY"),
                    },
                )
                if tabela_issqn["Alíquota ISSQN (%)"].isna().any():
                    st.warning(
                        "Uma ou mais classificações não têm alíquota informada na publicação oficial. "
                        "Confirme a regra com o município antes da emissão."
                    )
                if tabela_issqn["Código de Tributação Nacional"].duplicated().any():
                    st.warning(
                        "A publicação contém mais de uma regra vigente para o mesmo código. "
                        "As alternativas foram preservadas para conferência."
                    )

        st.divider()
        st.markdown("### Manual personalizado do Emissor Nacional")
        st.caption(
            "Gere um PDF com o passo a passo ilustrado e uma tabela das classificações nacionais "
            "compatíveis com os itens LC 116 selecionados."
        )
        if not empresa_issqn:
            st.info("Consulte um CNPJ na etapa Empresa para habilitar o manual personalizado.")
        else:
            relatorio_empresa = st.session_state.relatorio_cnpj
            itens_empresa: list[str] = []
            rotulos_itens: dict[str, str] = {}
            if (
                isinstance(relatorio_empresa, pd.DataFrame)
                and not relatorio_empresa.empty
                and "Item LC 116" in relatorio_empresa.columns
            ):
                colunas_disponiveis = ["Item LC 116"]
                if "Descrição LC 116" in relatorio_empresa.columns:
                    colunas_disponiveis.append("Descrição LC 116")
                colunas_itens = relatorio_empresa[colunas_disponiveis].drop_duplicates()
                for _, linha_item in colunas_itens.iterrows():
                    codigo_item = motor.normalizar_codigo_servico(linha_item["Item LC 116"])
                    if codigo_item and codigo_item not in itens_empresa:
                        itens_empresa.append(codigo_item)
                        descricao_item = str(linha_item.get("Descrição LC 116", "")).strip()
                        rotulos_itens[codigo_item] = (
                            f"{codigo_item} — {descricao_item}" if descricao_item else codigo_item
                        )
            if item_selecionado:
                item_normalizado = motor.normalizar_codigo_servico(item_selecionado)
                if item_normalizado and item_normalizado not in itens_empresa:
                    itens_empresa.append(item_normalizado)
                    rotulos_itens[item_normalizado] = item_normalizado
            itens_empresa.sort(key=lambda valor: [int(parte) for parte in valor.split(".")])

            if not itens_empresa:
                st.warning(
                    "Os CNAEs deste CNPJ não produziram itens LC 116 para compor o manual. "
                    "Selecione primeiro um serviço na Consulta individual."
                )
            else:
                padrao_manual = (
                    [motor.normalizar_codigo_servico(item_selecionado)]
                    if motor.normalizar_codigo_servico(item_selecionado) in itens_empresa
                    else itens_empresa[: min(3, len(itens_empresa))]
                )
                itens_manual = st.multiselect(
                    "Itens LC 116 que serão explicados no manual",
                    itens_empresa,
                    default=padrao_manual,
                    max_selections=10,
                    format_func=lambda codigo: rotulos_itens.get(codigo, codigo),
                    help="Confirme os itens correspondentes aos serviços efetivamente prestados.",
                )
                try:
                    classificacoes_manual = (
                        manual.classificacoes_por_itens(itens_manual) if itens_manual else []
                    )
                except manual.ManualNFSeError as erro:
                    st.error(str(erro))
                    classificacoes_manual = []
                st.write(
                    f"O PDF incluirá **{len(classificacoes_manual)} classificação(ões) nacional(is)** "
                    "com descrição oficial e alíquota municipal quando disponível."
                )

                assinatura_manual = (
                    str(empresa_issqn.get("cnpj", "")),
                    tuple(itens_manual),
                    data_issqn.isoformat(),
                    codigo_ibge_issqn,
                    municipio_issqn,
                    uf_issqn,
                )
                if st.button(
                    "Gerar manual personalizado",
                    type="primary",
                    width="stretch",
                    disabled=not itens_manual,
                ):
                    try:
                        with st.spinner("Montando o manual com imagens e classificações..."):
                            consulta_manual = issqn.consultar_aliquotas(
                                codigo_ibge=codigo_ibge_issqn,
                                municipio=municipio_issqn,
                                uf=uf_issqn,
                                data_referencia=data_issqn,
                            )
                            pdf_manual = manual.gerar_manual_nfse(
                                empresa_issqn,
                                itens_manual,
                                consulta_manual["registros"],
                            )
                        st.session_state.arquivo_manual_nfse = {
                            "assinatura": assinatura_manual,
                            "conteudo": pdf_manual,
                            "nome": manual.nome_arquivo_manual(empresa_issqn),
                        }
                    except (issqn.BaseISSQNError, manual.ManualNFSeError) as erro:
                        st.error(str(erro))

                arquivo_manual = st.session_state.arquivo_manual_nfse
                if arquivo_manual and arquivo_manual.get("assinatura") == assinatura_manual:
                    st.success("Manual personalizado preparado com sucesso.")
                    st.download_button(
                        "Baixar manual de emissão da NFS-e",
                        arquivo_manual["conteudo"],
                        arquivo_manual["nome"],
                        "application/pdf",
                        width="stretch",
                    )
                elif arquivo_manual:
                    st.info(
                        "Os parâmetros do manual mudaram. Clique em gerar novamente para atualizar o PDF."
                    )

        st.caption(
            f"Base derivada dos CSVs oficiais · gerada em {resumo_issqn['gerado_em']} · "
            "a localidade de incidência pode ser diferente do município do prestador conforme a LC 116."
        )
        st.link_button(
            "Conferir publicação oficial das alíquotas",
            issqn.FONTE_ALIQUOTAS,
            width="stretch",
        )


st.divider()
st.caption(
    "Ferramenta de apoio à análise · LC 214/2025 (texto compilado) · resultados sujeitos à legislação, notas técnicas e validação profissional vigentes."
)
