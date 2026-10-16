import streamlit as st


class LunaStyle:
    @staticmethod
    def apply():
        st.html("""
        <style>
        :root{--lv-bg:#111;--lv-surface:rgba(255,255,255,.055);--lv-control:rgba(255,255,255,.07);--lv-hover:rgba(255,255,255,.12);--lv-text:#f5f5f5;--lv-muted:#a3a3a3;--lv-border:rgba(255,255,255,.14);--lv-strong:rgba(255,255,255,.34);--lv-soft:rgba(255,255,255,.09)}
        .stApp{color:var(--lv-text);background:radial-gradient(circle at 82% -10%,rgba(255,255,255,.07),transparent 30rem),var(--lv-bg)}
        .block-container{max-width:1180px;padding-top:2.35rem;padding-bottom:3rem} header[data-testid="stHeader"]{background:transparent} #MainMenu,footer,div[data-testid="stDecoration"]{display:none}
        div[data-testid="stHorizontalBlock"]:has(.lv-header){align-items:center;min-height:5.5rem;height:5.5rem;margin-bottom:.55rem}div[data-testid="stHorizontalBlock"]:has(.lv-header)>div:last-child .stButton>button{width:100%;min-height:2.625rem;white-space:nowrap}.lv-header{display:flex;align-items:center;gap:1rem;min-height:4.5rem;margin-bottom:1rem}.lv-mark{display:block;flex:0 0 5.75rem;width:5.75rem;height:4.5rem;border:0;border-radius:0;object-fit:contain;object-position:center;box-shadow:none}.lv-placeholder{display:grid;place-items:center;flex:0 0 5.75rem;width:5.75rem;height:4.5rem;border:0;font-size:2rem}.lv-title{margin:0;font-size:clamp(1.65rem,3vw,2.15rem);font-weight:720;letter-spacing:-.04em;line-height:1}.stApp .lv-subtitle{margin:.32rem 0 0;color:var(--lv-muted);font-size:.78rem;font-weight:400}
        div[data-testid="stTabs"] [data-baseweb="tab-list"]{display:flex;width:100%;gap:.35rem;margin:1.2rem 0 1.15rem;padding:.4rem;border:1px solid var(--lv-border);border-radius:.9rem;background:var(--lv-surface)}
        div[data-testid="stTabs"] [data-baseweb="tab"]{flex:1 1 0;width:25%;min-width:0;height:2.55rem;justify-content:center;padding:0 1rem;border:1px solid transparent;border-radius:.65rem;background:var(--lv-control);color:var(--lv-muted);transition:border-color 140ms ease,background 140ms ease,transform 140ms ease}
        div[data-testid="stTabs"] [data-baseweb="tab"] :is(p,span){color:var(--lv-muted)!important;-webkit-text-fill-color:var(--lv-muted)!important}
        div[data-testid="stTabs"] [data-baseweb="tab"]:hover{border-color:var(--lv-strong);background:var(--lv-hover);color:var(--lv-muted);transform:translateY(-1px)}
        div[data-testid="stTabs"] [data-baseweb="tab"]:hover :is(p,span,svg){color:var(--lv-muted)!important;fill:currentColor!important;-webkit-text-fill-color:var(--lv-muted)!important}
        div[data-testid="stTabs"] [aria-selected="true"]{border-color:var(--lv-strong);background:var(--lv-hover);color:var(--lv-muted)!important;box-shadow:0 0 0 1px var(--lv-border)}
        div[data-testid="stTabs"] [aria-selected="true"] *,div[data-testid="stTabs"] [aria-selected="true"] :is(p,span,svg),div[data-testid="stTabs"] [aria-selected="true"] [data-testid="stIconMaterial"]{color:var(--lv-muted)!important;fill:currentColor!important;-webkit-text-fill-color:var(--lv-muted)!important}
        div[data-testid="stTabs"] [data-baseweb="tab-highlight"]{display:none}
        div[data-testid="stVerticalBlockBorderWrapper"]>div{border-color:var(--lv-border);border-radius:14px;background:var(--lv-surface);box-shadow:0 10px 30px rgba(0,0,0,.12)}
        .light-card{padding:.2rem}.light-name{font-size:1.05rem;font-weight:650}.light-meta{color:var(--lv-muted);font-size:.72rem}.state-dot{display:inline-block;width:.55rem;height:.55rem;border-radius:50%;margin-right:.4rem;background:#666}.state-dot.on{background:#22c55e;box-shadow:0 0 12px #22c55e}.swatch{display:inline-block;width:1rem;height:1rem;border-radius:50%;margin-right:.35rem;vertical-align:-.15rem;border:1px solid var(--lv-border)}
        div[class*="st-key-edit_name_"] .stButton>button{justify-content:flex-start!important;width:auto!important;min-height:1.6rem!important;height:auto!important;padding:0!important;border:0!important;background:transparent!important;box-shadow:none!important;font-size:1.05rem!important;font-weight:650!important;text-align:left!important}
        div[class*="st-key-edit_name_"] .stButton>button:hover{color:#fff!important;text-decoration:underline;text-underline-offset:.2rem;background:transparent!important}
        div[class*="st-key-confirm_name_"] .stButton>button{min-width:2.5rem!important;padding:.35rem!important}
        .stButton>button{border:1px solid var(--lv-border)!important;border-radius:.65rem!important;background:var(--lv-control)!important;color:var(--lv-text)!important}.stButton>button:hover{border-color:var(--lv-strong)!important;background:var(--lv-hover)!important}
        div[data-testid="stForm"]{padding:1.1rem;border-color:var(--lv-border);border-radius:14px;background:var(--lv-surface)}
        @media(max-width:700px){.block-container{padding:.85rem .8rem 2rem}div[data-testid="stHorizontalBlock"]:has(.lv-header){flex-wrap:wrap!important}div[data-testid="stHorizontalBlock"]:has(.lv-header)>div[data-testid="stColumn"]{flex:1 1 100%!important;width:100%!important}.lv-header{flex-wrap:nowrap!important;gap:.65rem;min-width:0}.lv-header>div{min-width:0;flex:1 1 auto}.lv-placeholder,.lv-mark{flex:0 0 4.25rem;width:4.25rem;height:3.5rem}.lv-title{white-space:nowrap;font-size:clamp(1.55rem,8vw,2rem)}.lv-subtitle{display:none}}
        </style>""")
