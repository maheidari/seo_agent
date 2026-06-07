import streamlit as st
import tempfile
import os
import sys

# ============================================================
# تنظیمات صفحه
# ============================================================

st.set_page_config(
    page_title="SEO Agent | تحلیل سرچ کنسول",
    page_icon="📊",
    layout="centered"
)

st.markdown("""
<style>
    .main { direction: rtl; }
    .stButton > button {
        width: 100%;
        background: linear-gradient(135deg, #1a73e8, #0d47a1);
        color: white;
        border: none;
        padding: 12px;
        border-radius: 8px;
        font-size: 16px;
        font-weight: bold;
        cursor: pointer;
    }
    .stButton > button:hover { opacity: 0.9; }
    .result-box {
        background: #f0f7ff;
        border-right: 4px solid #1a73e8;
        padding: 15px 20px;
        border-radius: 8px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# هدر
# ============================================================

st.markdown("## 📊 SEO Agent")
st.markdown("فایل CSV سرچ کنسول رو آپلود کن و گزارش کامل بگیر.")
st.markdown("---")

# ============================================================
# ورودی‌ها
# ============================================================

api_key = st.text_input(
    "🔑 Groq API Key",
    type="password",
    placeholder="gsk_...",
    help="کلیدت رو از console.groq.com بگیر"
)

site_url = st.text_input(
    "🌐 آدرس سایت",
    placeholder="https://example.com",
    help="اختیاریه ولی توی گزارش نشون داده می‌شه"
)

uploaded_file = st.file_uploader(
    "📂 فایل CSV سرچ کنسول",
    type=["csv"],
    help="از GSC بخش Queries → Export → CSV"
)

# ============================================================
# اجرا
# ============================================================

if st.button("🚀 شروع تحلیل"):

    if not api_key:
        st.error("❌ لطفاً Groq API Key رو وارد کن.")
        st.stop()

    if not uploaded_file:
        st.error("❌ لطفاً فایل CSV رو آپلود کن.")
        st.stop()

    os.environ["GROQ_API_KEY"] = api_key

    # ذخیره فایل آپلود شده روی دیسک
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_csv:
        tmp_csv.write(uploaded_file.read())
        csv_path = tmp_csv.name

    html_path = csv_path.replace(".csv", "_report.html")

    # اجرای agent با نمایش پیشرفت
    with st.status("🤖 Agent داره کار می‌کنه...", expanded=True) as status:

        try:
            # override توابع print برای نمایش توی Streamlit
            original_print = __builtins__["print"] if isinstance(__builtins__, dict) else print

            log_lines = []

            def streamlit_print(*args, **kwargs):
                line = " ".join(str(a) for a in args)
                log_lines.append(line)
                if line.strip():
                    st.write(line)

            import builtins
            builtins.print = streamlit_print

            # import و اجرای agent
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "gsc_agent",
                os.path.join(os.path.dirname(__file__), "gsc_agent.py")
            )
            gsc_module = importlib.util.load_from_spec(spec)
            spec.loader.exec_module(gsc_module)

            gsc_module.run_gsc_agent(csv_path, site_url or "نامشخص")

            builtins.print = original_print
            status.update(label="✅ گزارش آماده شد!", state="complete")

        except Exception as e:
            builtins.print = original_print
            st.error(f"❌ خطا: {e}")
            os.unlink(csv_path)
            st.stop()

    # نمایش دکمه دانلود
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        st.success("✅ گزارش با موفقیت ساخته شد!")

        st.download_button(
            label="⬇️ دانلود گزارش HTML",
            data=html_content,
            file_name="seo_report.html",
            mime="text/html"
        )

        # پاکسازی فایل‌های موقت
        os.unlink(csv_path)
        os.unlink(html_path)

    else:
        st.error("❌ فایل گزارش ساخته نشد. دوباره امتحان کن.")

# ============================================================
# فوتر
# ============================================================

st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:#aaa; font-size:13px;'>SEO Agent | ساخته شده با ❤️</div>",
    unsafe_allow_html=True
)
