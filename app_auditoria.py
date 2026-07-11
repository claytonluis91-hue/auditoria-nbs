"""Interface Streamlit da Auditoria NBS."""

from __future__ import annotations

import importlib
import re
from typing import Any

import pandas as pd
import streamlit as st

import backend_fiscal as motor


# O Streamlit pode recarregar apenas este arquivo e manter uma versão anterior
# do backend em memória. Recarregamos o motor somente quando uma função exigida
# pela interface atual ainda não estiver disponível.
FUNCOES_MOTOR_OBRIGATORIAS = (
    "formatar_cnpj",
    "preparar_dados_empresa",
    "resumir_combinacoes",
    "filtrar_combinacoes",
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
      .status-ok { color:#086444; background:#dff4e9; border-radius:999px; padding:.2rem .65rem; font-weight:650; }
      .status-review { color:#805500; background:#fff1c7; border-radius:999px; padding:.2rem .65rem; font-weight:650; }
      div[data-testid="stMetric"] { background:#f8fbfd; border:1px solid var(--borda); padding:12px; border-radius:12px; }
      div[data-testid="stMetricValue"] { font-variant-numeric:tabular-nums; }
      [data-testid="stSidebar"] { border-right:1px solid var(--borda); }
      .stDataFrame { font-variant-numeric:tabular-nums; }
    </style>
    """,
    unsafe_allow_html=True,
)


ETAPAS = ["1 · Empresa", "2 · Classificação", "3 · Simulação", "4 · Relatórios"]
ESTADO_INICIAL = {
    "empresa_selecionada": None,
    "relatorio_cnpj": None,
    "relatorio_manual": None,
    "servico_selecionado": None,
    "grupo_selecionado": None,
    "ultima_simulacao": None,
    "servico_simulado": None,
    "arquivos_relatorio": None,
    "etapa_atual": ETAPAS[0],
    "etapa_pendente": None,
    "origem_classificacao": "CNPJ consultado",
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
    }


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
                                codigos, df_cnae, df, df_indop
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
            st.info("Sem CNPJ? Utilize a consulta manual na etapa Classificação.")
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
        if acao_1.button("Continuar para classificação", type="primary", width="stretch"):
            st.session_state.origem_classificacao = "CNPJ consultado"
            ir_para(ETAPAS[1])
        if acao_2.button("Consultar outro CNPJ", width="stretch"):
            limpar_empresa()
            st.rerun()


elif etapa == ETAPAS[1]:
    st.subheader("Classificação e candidatos NBS")
    st.caption("Analise uma visão resumida e abra os INDOPs somente quando precisar dos detalhes.")

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
            st.markdown("#### Consulta manual de CNAE")
            termo_manual = st.text_input(
                "Código, atividade ou item LC 116",
                placeholder="Ex.: 6201-5/01 ou desenvolvimento",
                key="termo_manual",
            )
            resultado_manual = motor.buscar_cnae(df_cnae, termo_manual) if termo_manual else pd.DataFrame()
            if termo_manual and resultado_manual.empty:
                st.warning("Nenhum CNAE correspondente foi localizado.")
            elif not resultado_manual.empty:
                st.dataframe(
                    resultado_manual[
                        ["cnae", "descricao_cnae", "item_lista_servico"]
                    ].rename(
                        columns={
                            "cnae": "CNAE",
                            "descricao_cnae": "Atividade",
                            "item_lista_servico": "Item LC 116",
                        }
                    ),
                    width="stretch",
                    hide_index=True,
                    height=260,
                )
                opcoes = sorted(resultado_manual["cnae_numeros"].unique())
                selecionados = st.multiselect(
                    "CNAEs para analisar",
                    opcoes,
                    default=opcoes[: min(10, len(opcoes))],
                    format_func=motor.formatar_cnae,
                )
                if st.button("Analisar CNAEs selecionados", type="primary", width="stretch"):
                    st.session_state.relatorio_manual = motor.gerar_combinacoes_cnae_nbs(
                        selecionados, df_cnae, df, df_indop
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
                    "Item LC 116",
                    "NBS",
                    "Descrição NBS",
                    "cClassTrib",
                    "Quantidade INDOP",
                    "Opções INDOP",
                    "Status do vínculo",
                ]
            ]
        else:
            tabela = filtradas[
                [
                    "CNAE",
                    "Item LC 116",
                    "NBS",
                    "Descrição NBS",
                    "cClassTrib",
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
                    st.write(f"**NBS:** {primeiro['NBS']}")
                    st.write(f"**Descrição:** {primeiro['Descrição NBS']}")
                    st.write(f"**Item LC 116:** {primeiro['Item LC 116']}")
                    st.write(f"**cClassTrib:** {primeiro['cClassTrib']}")
                    st.write(f"**Regra:** {primeiro['Classificação Tributária']}")
            with detalhe_2:
                st.dataframe(
                    grupo[["INDOP", "Detalhamento INDOP"]].drop_duplicates(),
                    width="stretch",
                    hide_index=True,
                    height=230,
                    column_config={"Detalhamento INDOP": st.column_config.TextColumn(width="large")},
                )
            if st.button("Usar esta NBS no simulador", type="primary", width="stretch"):
                novo_servico = servico_a_partir_combinacao(primeiro)
                if st.session_state.servico_selecionado != novo_servico:
                    st.session_state.ultima_simulacao = None
                    st.session_state.servico_simulado = None
                st.session_state.servico_selecionado = novo_servico
                ir_para(ETAPAS[2])
        else:
            st.info("Selecione uma linha da tabela para abrir os detalhes e continuar.")
    elif origem == "Consulta manual":
        st.markdown('<div class="empty-state"><strong>Inicie uma consulta manual.</strong><br>Pesquise um CNAE acima e selecione as atividades que deseja analisar.</div>', unsafe_allow_html=True)


elif etapa == ETAPAS[2]:
    st.subheader("Simulação tributária")
    servico = st.session_state.servico_selecionado
    if not servico:
        st.markdown('<div class="empty-state"><strong>Nenhuma NBS foi selecionada.</strong><br>Escolha um candidato na etapa Classificação antes de simular.</div>', unsafe_allow_html=True)
        if st.button("Ir para classificação", type="primary"):
            ir_para(ETAPAS[1])
    else:
        with st.container(border=True):
            st.write(f"**NBS {servico['NBS']} · Item LC 116 {servico['Item LC 116']}**")
            st.write(servico["DESCRIÇÃO NBS"])
            st.caption(f"cClassTrib {servico['cClassTrib']} · {servico.get('nome cClassTrib', '')}")

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
        st.markdown('<div class="empty-state"><strong>Não há resultados para exportar.</strong><br>Realize uma classificação por CNPJ ou consulta manual.</div>', unsafe_allow_html=True)
        if st.button("Ir para classificação", type="primary"):
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


st.divider()
st.caption(
    "Ferramenta de apoio à análise · LC 214/2025 (texto compilado) · resultados sujeitos à legislação, notas técnicas e validação profissional vigentes."
)
