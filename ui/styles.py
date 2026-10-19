import streamlit as st

from config import UIConfig


class LunaStyle:
    @staticmethod
    def apply():
        st.html("""
        <style>
        :root{--lv-on-orb:radial-gradient(circle at 38% 35%,#fffbea 0,#ffd27a 38%,#ff9a1f 100%);--lv-on-orb-glow:0 0 0 1.5px rgba(10,10,10,.85),0 0 5px 1px rgba(255,166,38,.95),0 0 12px 3px rgba(255,140,20,.6),0 2px 6px rgba(0,0,0,.9);--lv-bg:#111;--lv-surface:rgba(255,255,255,.055);--lv-control:rgba(255,255,255,.07);--lv-hover:rgba(255,255,255,.12);--lv-text:#f5f5f5;--lv-muted:#a3a3a3;--lv-border:rgba(255,255,255,.14);--lv-strong:rgba(255,255,255,.34);--lv-soft:rgba(255,255,255,.09)}
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
        div[data-testid="stTabs"] [data-baseweb="tab-border"]{display:none}
        div[data-testid="stVerticalBlockBorderWrapper"]>div{border-color:var(--lv-border);border-radius:14px;background:var(--lv-surface);box-shadow:0 10px 30px rgba(0,0,0,.12)}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero)>div{overflow:hidden;border-color:var(--lv-border);background:linear-gradient(180deg,rgba(255,255,255,.065),rgba(255,255,255,.035));box-shadow:0 14px 34px rgba(0,0,0,.25)}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.room-card-background)>div{position:relative;overflow:hidden;min-height:11rem;background:#171717;box-shadow:0 14px 34px rgba(0,0,0,.25)}
        .room-card-background{position:absolute;inset:0;z-index:0;background-position:center;background-repeat:no-repeat;background-size:cover;pointer-events:none}
        .room-card-background::after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(10,10,10,.84),rgba(10,10,10,.58));pointer-events:none}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.room-card-background) div[data-testid="stElementContainer"]:has(.room-card-background){display:contents!important;position:static!important;margin:0!important;padding:0!important}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.room-card-background) div[data-testid="stElementContainer"],div[data-testid="stVerticalBlockBorderWrapper"]:has(.room-card-background) div[data-testid="stHorizontalBlock"]{position:relative;z-index:1}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.room-card-background) :is(h1,h2,h3,p){text-shadow:0 2px 8px rgba(0,0,0,.9)}
        div[class*="st-key-room_header_"]{display:flex!important;align-items:center!important;justify-content:space-between!important;width:100%!important}
        div[class*="st-key-room_header_"] h3{margin:0!important;padding:0!important}
        div[class*="st-key-room_header_"] div[class*="st-key-dg"] button{width:2.25rem!important;min-width:2.25rem!important;height:2.25rem!important;min-height:2.25rem!important;padding:0!important}
        div[class*="st-key-room_light_row_"]{display:flex!important;align-items:center!important;justify-content:flex-start!important;gap:.4rem!important;flex-wrap:nowrap!important;width:100%!important;min-width:0!important;margin-top:.65rem!important}
        div[class*="st-key-room_light_row_"] div[data-testid="stPopover"] button{width:2.25rem!important;min-width:2.25rem!important;height:1.45rem!important;min-height:1.45rem!important;padding:0!important}
        div[class*="st-key-room_light_row_"] div[data-testid="stPopover"]{margin-left:.35rem;transform:translateY(.12rem)}
        div[class*="st-key-room_light_row_"] div[data-testid="stPopover"] button,div[class*="st-key-room_light_row_"] div[data-testid="stPopover"] button:hover,div[class*="st-key-room_light_row_"] div[data-testid="stPopover"] button:focus,div[class*="st-key-room_light_row_"] div[data-testid="stPopover"] button:active{border:0!important;outline:0!important;background:transparent!important;background-color:transparent!important;box-shadow:none!important}
        div[class*="st-key-room_light_row_"] div[data-testid="stPopover"] button svg{display:none!important}
        div[data-testid="stElementContainer"]:has(.room-light-removable-pills){display:none!important}
        div[class*="st-key-room_light_row_"] div[data-testid="stElementContainer"]:has(div[data-testid="stButtonGroup"]){flex:1 1 auto!important;min-width:0!important;overflow:hidden!important}
        div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"]{width:100%!important;min-width:0!important;padding:0 0 .3rem!important;overflow-x:auto!important;overflow-y:hidden!important;scrollbar-width:thin;scrollbar-color:var(--lv-strong) transparent;border:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important}
        div[class*="st-key-room_light_row_"] [data-baseweb="button-group"]{display:flex!important;flex-wrap:nowrap!important;width:max-content!important;min-width:max-content!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important}
        div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"] button{position:relative;display:flex!important;flex:0 0 11.5rem!important;flex-direction:column!important;align-items:flex-start!important;justify-content:center!important;width:11.5rem!important;min-width:11.5rem!important;max-width:11.5rem!important;height:3.65rem!important;min-height:3.65rem!important;padding:.5rem 1.65rem .5rem .72rem!important;font-size:.76rem!important;line-height:1.05rem!important;overflow:hidden;box-shadow:none!important;transition:border-color .15s ease,background-color .15s ease}
        div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"] button>div,div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"] button>span{display:block!important;max-width:100%!important;overflow:hidden!important;text-overflow:ellipsis!important;white-space:nowrap!important}
        div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"] button:nth-of-type(6n+1){--pill-accent:#fca5a5;--pill-fill:220,38,38;--pill-edge:248,113,113}
        div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"] button:nth-of-type(6n+2){--pill-accent:#fcd34d;--pill-fill:217,119,6;--pill-edge:251,191,36}
        div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"] button:nth-of-type(6n+3){--pill-accent:#93c5fd;--pill-fill:37,99,235;--pill-edge:96,165,250}
        div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"] button:nth-of-type(6n+4){--pill-accent:#6ee7b7;--pill-fill:5,150,105;--pill-edge:52,211,153}
        div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"] button:nth-of-type(6n+5){--pill-accent:#d8b4fe;--pill-fill:147,51,234;--pill-edge:192,132,252}
        div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"] button:nth-of-type(6n+6){--pill-accent:#67e8f9;--pill-fill:8,145,178;--pill-edge:34,211,238}
        div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"] button p{color:var(--pill-accent)!important;font-weight:650!important}div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"] button{color:var(--pill-accent)!important;background:linear-gradient(135deg,rgba(var(--pill-fill),.26),rgba(var(--pill-fill),.06))!important;border:1px solid rgba(var(--pill-edge),.16)!important;border-radius:12px!important;font-weight:650!important}
        div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"] button:hover{background:linear-gradient(135deg,rgba(var(--pill-fill),.34),rgba(var(--pill-fill),.09))!important;border-color:rgba(var(--pill-edge),.34)!important}
        div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"] button::before{content:var(--room-power-label) "          " var(--room-online-label);order:2;display:block;width:100%;min-height:1.35rem;margin-top:.18rem;padding:.22rem 0 .22rem 1.25rem;box-sizing:border-box;color:var(--lv-muted);font-size:.62rem;font-weight:500;line-height:.9rem;letter-spacing:0;white-space:pre;background-image:radial-gradient(circle at .62rem 50%,var(--room-power-orb) 0,.23rem,transparent .26rem),radial-gradient(circle at .62rem 50%,var(--room-power-glow) 0,transparent .62rem),radial-gradient(circle at 5.05rem 50%,var(--room-online-orb) 0,.23rem,transparent .26rem),radial-gradient(circle at 5.05rem 50%,var(--room-online-glow) 0,transparent .62rem);background-repeat:no-repeat}
        div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"] button::after{content:"×";position:absolute;top:.38rem;right:.48rem;color:currentColor;font-size:.82rem;line-height:1;opacity:0;transition:opacity .15s ease}
        div[class*="st-key-room_light_row_"] div[data-testid="stButtonGroup"] button:hover::after{opacity:1}
        div[class*="st-key-room_card_"]>div[data-testid="stVerticalBlockBorderWrapper"]>div{overflow:hidden!important}
        div[class*="st-key-room_card_"]{position:relative;overflow:hidden!important}
        div[class*="st-key-room_layout_"] div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-room_image_"]){min-height:9rem}
        div[class*="st-key-room_layout_"] div[data-testid="stColumn"]:has(div[class*="st-key-room_image_"]){position:relative!important}
        div[class*="st-key-room_image_"]{position:absolute!important;top:calc(1px - 1rem);bottom:calc(1px - 1rem);left:calc(1px - 1rem);right:0;width:auto!important;margin:0!important}
        div[class*="st-key-room_image_"] div[data-testid="stElementContainer"]:has(.room-card-image){position:absolute!important;inset:0;width:auto!important;margin:0!important}
        .room-card-image{position:absolute;inset:0;display:grid;place-items:center;background-color:#1d1d1d;background-position:center;background-repeat:no-repeat;background-size:cover;color:var(--lv-muted)}
        .room-card-image::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(10,10,10,.05),rgba(10,10,10,.82));pointer-events:none}
        div[class*="st-key-room_image_"] div[data-testid="stElementContainer"]:has(.room-image-power-on){position:absolute!important;top:.72rem;right:.72rem;z-index:5;width:.72rem!important;height:.72rem!important}
        .room-image-power-on{display:block;width:.72rem;height:.72rem;border-radius:50%;background:var(--lv-on-orb);box-shadow:var(--lv-on-orb-glow)}
        div[class*="st-key-edit_room_name_"]:not([class*="st-key-edit_room_name_form_"]){position:absolute!important;left:.75rem;top:.75rem;z-index:4;width:max-content!important;max-width:72%!important;transform:none!important}
        div[class*="st-key-edit_room_name_"]:not([class*="st-key-edit_room_name_form_"]) button{justify-content:flex-start!important;width:auto!important;max-width:100%!important;min-height:1.6rem!important;height:auto!important;padding:.5rem .88rem!important;border:1px solid rgba(255,255,255,.16)!important;border-radius:.7rem!important;background:rgba(38,38,38,.78)!important;color:#e0e0e0!important;box-shadow:0 4px 14px rgba(0,0,0,.34)!important;backdrop-filter:blur(8px);font-size:1.05rem!important;font-weight:650!important;text-align:left!important;text-decoration:none!important;text-shadow:0 1px 8px rgba(0,0,0,.9)!important;overflow:hidden!important;text-overflow:ellipsis!important;white-space:nowrap!important}
        div[class*="st-key-edit_room_name_"]:not([class*="st-key-edit_room_name_form_"]) button:hover{color:#e0e0e0!important;text-decoration:none!important;border-color:rgba(255,255,255,.22)!important;background:rgba(44,44,44,.82)!important}
        div[class*="st-key-edit_room_name_form_"]{position:absolute!important;left:.75rem;top:.75rem;z-index:6;width:calc(100% - 1.5rem)!important;transform:none!important}
        div[class*="st-key-edit_room_name_form_"] div[data-testid="stForm"]{padding:0!important;border:0!important;background:transparent!important;box-shadow:none!important}
        div[class*="st-key-edit_room_name_form_"] div[data-testid="stHorizontalBlock"]{gap:.45rem!important}
        div[class*="st-key-edit_room_name_form_"] input{background:rgba(26,26,26,.9)!important;backdrop-filter:blur(8px)}
        div[class*="st-key-edit_room_name_form_"] [data-testid="InputInstructions"] span:first-child{display:none!important}
        div[class*="st-key-edit_room_name_form_"] [data-testid="InputInstructions"] span:nth-child(2)::before{display:none!important}
        .room-card-image .material-symbols-rounded{position:relative;z-index:1;font-family:"Material Symbols Rounded"!important;font-size:2rem;font-weight:normal;font-style:normal;font-feature-settings:"liga";-webkit-font-feature-settings:"liga"}
        .light-card-hero{position:relative;height:8.25rem;margin:-1rem -1rem .8rem;background-color:#1d1d1d;background-position:center;background-repeat:no-repeat;background-size:cover;overflow:hidden}
        .light-card-hero::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(10,10,10,.05),rgba(10,10,10,.82));pointer-events:none}
        .light-card-power-on{position:absolute;top:.75rem;right:.75rem;z-index:3;display:block;width:.72rem;height:.72rem;overflow:hidden;border-radius:50%;background:var(--lv-on-orb);color:transparent;font-size:0;line-height:0;box-shadow:var(--lv-on-orb-glow)}
        .light-card-status{position:absolute;right:.7rem;bottom:.65rem;z-index:2;display:inline-flex;align-items:center;gap:.35rem;padding:.3rem .55rem;border:1px solid var(--lv-border);border-radius:999px;background:rgba(17,17,17,.78);backdrop-filter:blur(8px);color:var(--lv-muted);font-size:.7rem;font-weight:600}
        .light-card-status i{display:block;width:.45rem;height:.45rem;border-radius:50%;background:#666}
        .light-card-status.online i{background:#22c55e;box-shadow:0 0 10px rgba(34,197,94,.8)}
        .light-stats-row{display:flex;align-items:center;justify-content:space-between;gap:.65rem;width:100%;min-height:3rem;margin-bottom:0;padding:.5rem .7rem;border:1px solid var(--lv-border);border-radius:.7rem;background:rgba(18,18,22,.72);box-shadow:0 8px 22px rgba(0,0,0,.18);box-sizing:border-box}
        .scheme-preview{height:2.6rem;margin:-.15rem 0 .65rem;border-radius:.6rem;box-shadow:inset 0 0 0 1px rgba(255,255,255,.08),0 6px 18px rgba(0,0,0,.25)}
        .scheme-title{display:flex;align-items:center;flex-wrap:wrap;gap:.4rem;color:var(--lv-text);font-size:.98rem;font-weight:650}
        .scheme-details{margin:.2rem 0 .55rem;color:var(--lv-muted);font-size:.72rem}
        .scheme-badge{padding:.12rem .45rem;border:1px solid var(--lv-border);border-radius:999px;color:var(--lv-muted);font-size:.6rem;font-weight:500}
        .scheme-badge.playing{border-color:rgba(255,190,85,.45);color:#ffbe55}
        div[class*="st-key-sequence_step_"]{position:relative!important}
        div[class*="st-key-sequence_step_"] div[class*="st-key-seq_"][class*="_remove"]{position:absolute!important;top:.3rem;right:.3rem;z-index:2;width:auto!important}
        div[class*="st-key-seq_"][class*="_remove"] button,div[class*="st-key-seq_"][class*="_remove"] button:hover{width:2.25rem!important;min-width:2.25rem!important;height:2.25rem!important;padding:0!important;border:0!important;background:transparent!important;box-shadow:none!important}
        .scheme-step-title{color:var(--lv-text);font-size:.85rem;font-weight:650}
        div[class*="st-key-light_mode_body_"]{min-height:5.45rem;justify-content:center}
        div[class*="st-key-room_actions_"]{justify-content:flex-end!important;gap:.9rem!important}
        div[class*="st-key-room_actions_"]>div[data-testid="stLayoutWrapper"]{flex:0 0 auto!important;width:auto!important}
        div[data-testid="stPopoverBody"]:has(.room-scheme-heading){min-width:25rem!important}
        div[data-testid="stPopoverBody"]:has(.room-scheme-heading) button{justify-content:flex-start!important;white-space:nowrap!important;font-size:.8rem!important}
        div[data-testid="stPopoverBody"]:has(.room-scheme-heading) button p{white-space:nowrap!important}
        div[class*="st-key-room_scheme_"] div[data-testid="stPopover"] button{min-width:4.25rem!important;padding:0 1rem!important;min-height:2.25rem!important;height:2.25rem!important;border:1px solid var(--lv-border)!important;border-radius:.65rem!important;background:var(--lv-control)!important;font-size:.78rem!important}
        .room-scheme-heading{margin:.35rem 0 .1rem;color:var(--lv-muted);font-size:.7rem;font-weight:600;letter-spacing:.04em;text-transform:uppercase}
        div[class*="st-key-temp_presets_"]{flex-wrap:nowrap!important;gap:.35rem!important;margin:-.1rem 0 .2rem}
        div[class*="st-key-temp_preset_"] button p{font-size:.66rem!important;line-height:1!important;overflow:hidden;text-overflow:ellipsis}
        div[class*="st-key-temp_presets_"]>div{flex:1 1 0!important;min-width:0!important;width:auto!important}
        div[class*="st-key-temp_preset_"] button{width:100%!important;min-height:1.75rem!important;height:1.75rem!important;padding:0 .25rem!important;border:1px solid var(--lv-border)!important;border-radius:.65rem!important;font-size:.68rem!important;font-weight:600!important;white-space:nowrap!important}
        .st-key-header_actions{flex-wrap:nowrap!important;width:100%!important}
        .st-key-header_actions .st-key-header_refresh_lights{flex:0 0 auto!important;width:auto!important}
        .st-key-header_actions .st-key-header_refresh_lights button{width:2.625rem!important;min-width:2.625rem!important;height:2.625rem!important;padding:0!important}
        .st-key-header_actions .st-key-header_all_lights_power{flex:1 1 auto!important;min-width:0!important}
        .st-key-all_lights_bar{margin-top:1rem;margin-bottom:1rem}
        .st-key-all_lights_bar .light-stats-row{min-height:6.2rem}
        .st-key-all_lights_mode [data-baseweb="button-group"],.st-key-all_lights_mode div[data-testid="stButtonGroup"]{flex-wrap:nowrap!important}
        .st-key-all_lights_mode button{padding-inline:.7rem!important}
        .st-key-all_lights_bar [data-testid="stMarkdownContainer"]:has(>.light-stats-row){margin-bottom:0!important}
        .st-key-all_lights_brightness_box,.st-key-all_lights_color_box{justify-content:center;min-height:6.2rem;padding:.35rem .7rem;border:1px solid var(--lv-border);border-radius:.7rem;background:rgba(18,18,22,.72);box-shadow:0 8px 22px rgba(0,0,0,.18);box-sizing:border-box}
        .inline-control-icon{display:flex;justify-content:center;align-items:center;color:var(--lv-muted);font-family:"Material Symbols Rounded"!important;font-size:1.3rem;line-height:1;font-weight:normal;font-style:normal;font-feature-settings:"liga";-webkit-font-feature-settings:"liga"}
        .light-stat-card{display:flex;align-items:center;justify-content:flex-start;gap:.42rem;min-height:2rem;padding:0;border:0;background:transparent;box-shadow:none;white-space:nowrap}
        .light-stat-card .material-symbols-rounded{font-family:"Material Symbols Rounded"!important;font-weight:normal;font-style:normal;font-size:1.35rem;line-height:1;font-feature-settings:"liga";-webkit-font-feature-settings:"liga"}
        .light-stat-card .total{color:#ffbe55}.light-stat-card>div{display:flex;align-items:baseline;gap:.32rem;line-height:1}.light-stat-card strong{color:var(--lv-text);font-size:.9rem}.light-stat-card small{color:var(--lv-muted);font-size:.66rem}.status-orb{display:block;width:.72rem;height:.72rem;border-radius:50%}.status-orb.on{background:#ffbe55;box-shadow:0 0 10px rgba(255,190,85,.55)}.status-orb.online{background:#22c55e;box-shadow:0 0 12px rgba(34,197,94,.75)}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) .light-meta-row{display:flex;align-items:center;justify-content:space-between;gap:.5rem;margin:-.15rem 0 .7rem;transform:translateY(-.45rem)}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) .light-meta{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .light-room-membership{display:inline-flex;flex:0 1 auto;min-width:0;align-items:center;gap:.25rem;padding:.18rem .4rem;border-radius:999px;background:rgba(255,255,255,.07);color:var(--lv-muted);font-size:.65rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .light-room-membership .material-symbols-rounded{flex:0 0 auto;font-family:"Material Symbols Rounded"!important;font-size:.8rem;line-height:1;font-weight:normal;font-style:normal;font-feature-settings:"liga";-webkit-font-feature-settings:"liga"}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero)>div{position:relative}
        [class*="st-key-edit_name_"]:not([class*="st-key-edit_name_form_"]){position:relative!important;z-index:4!important;width:max-content!important;max-width:60%!important;margin:-7.65rem auto 3.6rem .75rem!important}
        [class*="st-key-edit_name_form_"]{position:relative!important;z-index:4!important;width:calc(100% - 1.5rem)!important;margin:-7.65rem .75rem 3.6rem!important}
        [class*="st-key-edit_name_form_"] div[data-testid="stHorizontalBlock"]{gap:.5rem!important}
        [class*="st-key-edit_name_form_"] div[data-testid="stForm"]{padding:0!important;border:0!important;background:transparent!important;box-shadow:none!important}
        [class*="st-key-edit_name_form_"] input{background:rgba(26,26,26,.88)!important;backdrop-filter:blur(8px)}
        [class*="st-key-edit_name_form_"] [data-testid="InputInstructions"] span:first-child{display:none!important}
        [class*="st-key-edit_name_form_"] [data-testid="InputInstructions"] span:nth-child(2)::before{display:none!important}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) [class*="st-key-edit_name_"]:not([class*="st-key-edit_name_form_"]) button{padding:.38rem .72rem!important;border:1px solid rgba(255,255,255,.14)!important;border-radius:.65rem!important;background:rgba(8,8,8,.76)!important;color:#e0e0e0!important;box-shadow:0 4px 14px rgba(0,0,0,.28)!important;backdrop-filter:blur(7px);text-shadow:0 1px 8px rgba(0,0,0,.9)!important}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) div[class*="st-key-delete_light_"]{display:flex!important;justify-content:flex-end!important;width:100%!important;height:2.15rem!important;margin:0!important}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) div[class*="st-key-delete_light_"] :is(div[data-testid="stButton"],.stButton){display:flex!important;justify-content:flex-end!important;width:100%!important}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) div[class*="st-key-delete_light_"] .stButton>button,div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) div[class*="st-key-delete_light_"] .stButton>button:hover{width:2.15rem!important;min-width:2.15rem!important;height:2.15rem!important;min-height:2.15rem!important;padding:0!important;border:0!important;background:transparent!important;box-shadow:none!important;color:#d8d8d8!important}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) div[class*="st-key-delete_light_"] button{margin-left:auto!important;margin-right:0!important}
        div[data-testid="stCheckbox"] label[data-baseweb="checkbox"]{align-items:center!important;gap:.38rem!important}
        div[data-testid="stCheckbox"] label[data-baseweb="checkbox"]::before{content:"Off";color:var(--lv-muted)!important;font-size:.9rem;line-height:1}
        div[data-testid="stCheckbox"] label[data-baseweb="checkbox"]>div:last-child{color:var(--lv-muted)!important}
        div[data-testid="stCheckbox"] label[data-baseweb="checkbox"]>div:first-of-type{background-color:#484848!important}
        div[data-testid="stCheckbox"] label[data-baseweb="checkbox"]>div:first-of-type>div{background-color:#b8b8b8!important}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) div[data-testid="stSlider"]{padding-top:.1rem}
        div[class*="st-key-preset_color_"]{display:flex!important;justify-content:center!important}
        div[class*="st-key-preset_color_"] button{width:100%!important;min-width:0!important;height:1.75rem!important;min-height:1.75rem!important;padding:0 .25rem!important;border-radius:.65rem!important;box-shadow:none!important;font-weight:600!important;white-space:nowrap!important;transition:border-color .15s ease,background-color .15s ease,transform .15s ease}
        div[class*="st-key-preset_color_"] button p{font-size:.66rem!important;line-height:1!important;overflow:hidden;text-overflow:ellipsis}
        div[class*="st-key-color_presets_"]{flex-wrap:nowrap!important;gap:.35rem!important;margin:-.1rem 0 .2rem}
        div[class*="st-key-color_presets_"]>div{flex:1 1 0!important;min-width:0!important;width:auto!important}
        div[class*="st-key-preset_color_"] button:hover{transform:scale(1.06)}
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
        [class*="st-key-edit_name_"]:not([class*="st-key-edit_name_form_"]) .stButton>button,[class*="st-key-edit_name_"]:not([class*="st-key-edit_name_form_"]).stButton>button{justify-content:flex-start!important;width:auto!important;min-height:1.6rem!important;height:auto!important;padding:.5rem .88rem!important;border:1px solid rgba(255,255,255,.16)!important;border-radius:.7rem!important;background:rgba(38,38,38,.72)!important;color:#e0e0e0!important;box-shadow:0 4px 14px rgba(0,0,0,.26)!important;backdrop-filter:blur(8px);font-size:1.05rem!important;font-weight:650!important;text-align:left!important;text-decoration:none!important;text-shadow:0 1px 8px rgba(0,0,0,.9)!important}
        [class*="st-key-edit_name_"]:not([class*="st-key-edit_name_form_"]) .stButton>button:hover,[class*="st-key-edit_name_"]:not([class*="st-key-edit_name_form_"]).stButton>button:hover{color:#e0e0e0!important;text-decoration:none!important;border-color:rgba(255,255,255,.22)!important;background:rgba(44,44,44,.78)!important}
        div[class*="st-key-confirm_name_"] .stButton>button{min-width:2.5rem!important;padding:.35rem!important}
        .stButton>button{border:1px solid var(--lv-border)!important;border-radius:.65rem!important;background:var(--lv-control)!important;color:var(--lv-text)!important}.stButton>button:hover{border-color:var(--lv-strong)!important;background:var(--lv-hover)!important}
        div[class*="st-key-delete_light_"] button,div[class*="st-key-delete_light_"] button:hover,div[class*="st-key-delete_light_"] button:focus,div[class*="st-key-delete_light_"] button:active{border:0!important;outline:0!important;background:transparent!important;background-color:transparent!important;box-shadow:none!important}
        div[class*="st-key-dg"] button,div[class*="st-key-dg"] button:hover,div[class*="st-key-dg"] button:focus,div[class*="st-key-dg"] button:active{border:0!important;outline:0!important;background:transparent!important;background-color:transparent!important;box-shadow:none!important}
        div[data-testid="stMultiSelect"] div[data-baseweb="select"]>div{border-color:var(--lv-border)!important;background:#181818!important}
        div[data-testid="stMultiSelect"] span[data-baseweb="tag"]{border:1px solid rgba(255,255,255,.14)!important;background:#303030!important;color:var(--lv-text)!important;-webkit-text-fill-color:var(--lv-text)!important}
        div[data-testid="stMultiSelect"] span[data-baseweb="tag"] *{color:var(--lv-text)!important;fill:var(--lv-text)!important;-webkit-text-fill-color:var(--lv-text)!important}
        div[data-testid="stForm"]{padding:1.1rem;border-color:var(--lv-border);border-radius:14px;background:var(--lv-surface)}
        [data-testid="InputInstructions"] span:first-child{display:none!important}
        [data-testid="InputInstructions"] span:nth-child(2)::before{display:none!important}
        @media(max-width:700px){.block-container{padding:.85rem .8rem 2rem}div[data-testid="stHorizontalBlock"]:has(.lv-header){flex-wrap:wrap!important}div[data-testid="stHorizontalBlock"]:has(.lv-header)>div[data-testid="stColumn"]{flex:1 1 100%!important;width:100%!important}.lv-header{flex-wrap:nowrap!important;gap:.65rem;min-width:0}.lv-header>div{min-width:0;flex:1 1 auto}.lv-placeholder,.lv-mark{flex:0 0 4.25rem;width:4.25rem;height:3.5rem}.lv-title{white-space:nowrap;font-size:clamp(1.55rem,8vw,2rem)}.lv-subtitle{display:none}div[data-testid="stTabs"] [data-baseweb="tab"]{padding:0 .55rem!important}div[data-testid="stTabs"] [data-baseweb="tab"] p{display:none!important}div[data-testid="stTabs"] [data-baseweb="tab"]::before{display:block;font-family:"Material Symbols Rounded"!important;font-size:1.25rem!important;font-weight:normal;font-style:normal;line-height:1!important;color:var(--lv-muted)!important;-webkit-text-fill-color:var(--lv-muted)!important;font-feature-settings:"liga";-webkit-font-feature-settings:"liga"}div[data-testid="stTabs"] [data-baseweb="tab"]:nth-of-type(1)::before{content:"lightbulb"}div[data-testid="stTabs"] [data-baseweb="tab"]:nth-of-type(2)::before{content:"meeting_room"}div[data-testid="stTabs"] [data-baseweb="tab"]:nth-of-type(3)::before{content:"palette"}div[data-testid="stTabs"] [data-baseweb="tab"]:nth-of-type(4)::before{content:"schedule"}.light-stats-row{width:100%}div[data-testid="stHorizontalBlock"]:has(.find-lights-card){flex-wrap:wrap!important}.find-lights-icon{width:3rem;height:3rem}.find-lights-card h2{font-size:1.1rem}.find-lights-card p{white-space:normal!important}.st-key-scan_for_lights{width:100%}div[class*="st-key-light_color_controls_"] div[data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:.35rem!important}div[class*="st-key-light_color_controls_"] div[data-testid="stColumn"]{flex:1 1 0!important;min-width:0!important;width:auto!important}div[class*="st-key-light_color_controls_"] div[data-testid="stColumn"]:first-child{flex:0 0 1.6rem!important;min-width:1.6rem!important;width:1.6rem!important}div[class*="st-key-light_color_controls_"] div[data-testid="stColumn"]:nth-child(2){flex:1.35 1 0!important}div[class*="st-key-light_card_actions_"] div[data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important}div[class*="st-key-light_card_actions_"] div[data-testid="stColumn"]:first-child{flex:8 1 0!important;min-width:0!important;width:auto!important}div[class*="st-key-light_card_actions_"] div[data-testid="stColumn"]:last-child{flex:0 0 2.15rem!important;min-width:2.15rem!important;width:2.15rem!important;margin-left:auto!important}div[class*="st-key-room_card_"]>div[data-testid="stVerticalBlockBorderWrapper"]>div>div[data-testid="stHorizontalBlock"]{flex-wrap:wrap!important}div[class*="st-key-room_card_"]>div[data-testid="stVerticalBlockBorderWrapper"]>div>div[data-testid="stHorizontalBlock"]>div[data-testid="stColumn"]{flex:1 1 100%!important;width:100%!important}}
        @media(max-width:700px){
            .st-key-room_creation_tabs div[data-testid="stTabs"] [data-baseweb="tab"]:nth-of-type(1)::before{content:"meeting_room"}
            .st-key-room_creation_tabs div[data-testid="stTabs"] [data-baseweb="tab"]:nth-of-type(2)::before{content:"group"}
            .st-key-scheme_sections div[data-testid="stTabs"] [data-baseweb="tab"]:nth-of-type(1)::before{content:"palette"}
            .st-key-scheme_sections div[data-testid="stTabs"] [data-baseweb="tab"]:nth-of-type(2)::before{content:"lens"}
            .st-key-scheme_sections div[data-testid="stTabs"] [data-baseweb="tab"]:nth-of-type(3)::before{content:"timeline"}
            .st-key-scheme_sections div[data-testid="stTabs"] [data-baseweb="tab"]:nth-of-type(4)::before{content:"swap_horiz"}
            div[class*="st-key-room_layout_"]{width:100%!important}
            div[class*="st-key-room_layout_"] div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-room_image_"]){position:relative!important;flex-direction:column!important;flex-wrap:nowrap!important;padding-top:9rem!important;gap:0!important}
            div[class*="st-key-room_layout_"] div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-room_image_"])>div[data-testid="stColumn"]{position:static!important;flex:0 0 auto!important;width:100%!important;min-width:100%!important;max-width:100%!important}
            div[class*="st-key-room_image_"]{left:calc(1px - 1rem)!important;right:auto!important;bottom:auto!important;width:calc(100% + 2rem - 2px)!important;max-width:none!important;height:calc(9.25rem - 1px)!important}
        }
        @media(max-width:700px){div[class*="st-key-icon_slider_"] div[data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important}div[class*="st-key-icon_slider_"] div[data-testid="stColumn"]:first-child{flex:0 0 1.6rem!important;min-width:1.6rem!important;width:1.6rem!important}div[class*="st-key-icon_slider_"] div[data-testid="stColumn"]:last-child{flex:1 1 0!important;min-width:0!important;width:auto!important}}
        @media(max-width:700px){.st-key-all_lights_bar .light-stats-row,.st-key-all_lights_brightness_box{min-height:3.6rem!important}.st-key-all_lights_color_box{min-height:0!important}.st-key-all_lights_color_box div[data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important}.st-key-all_lights_color_box div[data-testid="stHorizontalBlock"]>div[data-testid="stColumn"]:first-child{flex:0 0 auto!important;width:auto!important;min-width:0!important}.st-key-all_lights_color_box div[data-testid="stHorizontalBlock"]>div[data-testid="stColumn"]:last-child{flex:1 1 0!important;min-width:0!important;width:auto!important}}
        </style>""")
        st.html(f"<style>{LunaStyle.preset_swatch_rules()}</style>")

    @staticmethod
    def preset_swatch_rules() -> str:
        """Tint each preset like the Rooms tab light pills, with its name in its color."""
        rules = []
        for color in UIConfig.PRESET_COLORS:
            red, green, blue = (int(color[index : index + 2], 16) for index in (1, 3, 5))
            selector = f'div[class*="st-key-preset_color_"][class*="_{color[1:]}"] button'
            rules.append(
                f"{selector},{selector} *{{color:{color}!important;-webkit-text-fill-color:{color}!important}}"
                f"{selector}{{background:rgba({red},{green},{blue},.18)!important;border:1px solid rgba({red},{green},{blue},.35)!important}}"
                f"{selector}:hover{{background:rgba({red},{green},{blue},.28)!important;border-color:rgba({red},{green},{blue},.6)!important}}"
            )
        return "".join(rules)
