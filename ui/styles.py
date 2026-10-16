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
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero)>div{overflow:hidden;border-color:var(--lv-border);background:linear-gradient(180deg,rgba(255,255,255,.065),rgba(255,255,255,.035));box-shadow:0 14px 34px rgba(0,0,0,.25)}
        .light-card-hero{position:relative;height:8.25rem;margin:-1rem -1rem .8rem;background-color:#1d1d1d;background-position:center;background-size:cover;border-bottom:1px solid var(--lv-border)}
        .light-card-status{position:absolute;right:.7rem;bottom:.65rem;display:inline-flex;align-items:center;gap:.35rem;padding:.3rem .55rem;border:1px solid var(--lv-border);border-radius:999px;background:rgba(17,17,17,.78);backdrop-filter:blur(8px);color:var(--lv-muted);font-size:.7rem;font-weight:600}
        .light-card-status i{display:block;width:.45rem;height:.45rem;border-radius:50%;background:#666}
        .light-card-status.online i{background:#22c55e;box-shadow:0 0 10px rgba(34,197,94,.8)}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) .light-meta{margin:-.15rem 0 .25rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero)>div{position:relative}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) div[class*="st-key-edit_name_"]{position:absolute;left:.75rem;top:6.15rem;z-index:4;max-width:60%}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) div[class*="st-key-edit_name_"] .stButton>button{color:#e0e0e0!important;text-shadow:0 1px 8px rgba(0,0,0,.9)!important}
        div[data-testid="stToggle"] input:checked+div{background:#8f8f8f!important}
        div[data-testid="stToggle"] label:has(input:checked) [data-baseweb="checkbox"]>div{background:#8f8f8f!important}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) div[data-testid="stSlider"]{padding-top:.1rem}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) .stButton>button{min-height:2.55rem}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.find-lights-card)>div{padding:1rem 1.15rem;border-color:var(--lv-border);background:var(--lv-surface);box-shadow:0 12px 30px rgba(0,0,0,.18),inset 0 1px 0 rgba(255,255,255,.025)}
        .find-lights-icon{display:grid;place-items:center;width:3.4rem;height:3.4rem;border:1px solid var(--lv-strong);border-radius:.85rem;background:var(--lv-control);box-shadow:0 8px 20px rgba(0,0,0,.2);transform:translateY(-.3rem)}
        .find-lights-icon .material-symbols-rounded{font-family:"Material Symbols Rounded"!important;font-weight:normal;font-style:normal;font-size:1.75rem;line-height:1;letter-spacing:normal;text-transform:none;white-space:nowrap;word-wrap:normal;direction:ltr;font-feature-settings:"liga";-webkit-font-feature-settings:"liga";background:linear-gradient(145deg,#f5f5f5 15%,#a3a3a3 55%,#ffffff 90%);background-clip:text;-webkit-background-clip:text;color:transparent!important;-webkit-text-fill-color:transparent}
        .find-lights-card h2{margin:0!important;padding:0!important;color:var(--lv-text);font-size:1.35rem;font-weight:700;letter-spacing:-.025em;line-height:1.15}
        .stApp .find-lights-card p{margin:.18rem 0 0!important;padding:0!important;color:var(--lv-muted);font-size:.68rem;line-height:1.2;white-space:nowrap}
        .st-key-scan_for_lights .stButton>button{min-height:3rem!important;border-color:var(--lv-strong)!important;background:#2b2b2b!important;background-image:none!important;font-weight:600!important;transition:border-color 140ms ease,background 140ms ease,transform 140ms ease!important}
        .st-key-scan_for_lights .stButton>button:hover{border-color:var(--lv-text)!important;background:var(--lv-hover)!important;transform:translateY(-1px)}
        .discovery-results-marker{display:none!important}
        details:has(.discovery-results-marker){margin-top:.35rem;border:1px solid var(--lv-border)!important;border-radius:.85rem!important;background:rgba(255,255,255,.025)!important}
        details:has(.discovery-results-marker)>summary{color:var(--lv-muted)!important}
        .light-card{padding:.2rem}.light-name{font-size:1.05rem;font-weight:650}.light-meta{color:var(--lv-muted);font-size:.72rem}.state-dot{display:inline-block;width:.55rem;height:.55rem;border-radius:50%;margin-right:.4rem;background:#666}.state-dot.on{background:#22c55e;box-shadow:0 0 12px #22c55e}.swatch{display:inline-block;width:1rem;height:1rem;border-radius:50%;margin-right:.35rem;vertical-align:-.15rem;border:1px solid var(--lv-border)}
        div[class*="st-key-edit_name_"] .stButton>button{justify-content:flex-start!important;width:auto!important;min-height:1.6rem!important;height:auto!important;padding:0!important;border:0!important;background:transparent!important;box-shadow:none!important;font-size:1.05rem!important;font-weight:650!important;text-align:left!important}
        div[class*="st-key-edit_name_"] .stButton>button:hover{color:#fff!important;text-decoration:underline;text-underline-offset:.2rem;background:transparent!important}
        div[class*="st-key-confirm_name_"] .stButton>button{min-width:2.5rem!important;padding:.35rem!important}
        .stButton>button{border:1px solid var(--lv-border)!important;border-radius:.65rem!important;background:var(--lv-control)!important;color:var(--lv-text)!important}.stButton>button:hover{border-color:var(--lv-strong)!important;background:var(--lv-hover)!important}
        div[data-testid="stForm"]{padding:1.1rem;border-color:var(--lv-border);border-radius:14px;background:var(--lv-surface)}
        @media(max-width:700px){.block-container{padding:.85rem .8rem 2rem}div[data-testid="stHorizontalBlock"]:has(.lv-header){flex-wrap:wrap!important}div[data-testid="stHorizontalBlock"]:has(.lv-header)>div[data-testid="stColumn"]{flex:1 1 100%!important;width:100%!important}.lv-header{flex-wrap:nowrap!important;gap:.65rem;min-width:0}.lv-header>div{min-width:0;flex:1 1 auto}.lv-placeholder,.lv-mark{flex:0 0 4.25rem;width:4.25rem;height:3.5rem}.lv-title{white-space:nowrap;font-size:clamp(1.55rem,8vw,2rem)}.lv-subtitle{display:none}div[data-testid="stHorizontalBlock"]:has(.find-lights-card){flex-wrap:wrap!important}.find-lights-icon{width:3rem;height:3rem}.find-lights-card h2{font-size:1.1rem}.find-lights-card p{white-space:normal!important}.st-key-scan_for_lights{width:100%}}
        </style>""")
