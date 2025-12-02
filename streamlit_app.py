"""
Streamlit Dashboard for App Review Insights Analyser

Monitor statistics for each layer and manage weekly pulses.
"""
import streamlit as st
import json
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from config.settings import settings
from layer_4_distribution.generate_email import EmailGenerator
from layer_4_distribution.email_sender import EmailSender
from layer_1_data_import.import_reviews import import_reviews
from layer_2_theme_extraction.classify_reviews import classify_all_reviews
from layer_3_content_generation.generate_pulse import generate_all_pulses
from utils.logger import get_logger

logger = get_logger(__name__)

# Page configuration
st.set_page_config(
    page_title="App Review Insights Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .layer-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: white;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    </style>
""", unsafe_allow_html=True)


def load_json_file(filepath: str) -> Optional[Dict[str, Any]]:
    """Load JSON file safely"""
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {filepath}: {e}")
        return None


def get_available_weeks() -> List[str]:
    """Get list of available weeks from pulse files"""
    pulses_dir = os.path.join(settings.DATA_DIR, "pulses")
    if not os.path.exists(pulses_dir):
        return []
    
    pulse_files = [
        f.replace('pulse_', '').replace('.json', '')
        for f in os.listdir(pulses_dir)
        if f.startswith('pulse_') and f.endswith('.json')
    ]
    return sorted(pulse_files, reverse=True)


def get_layer1_stats(week_key: str) -> Dict[str, Any]:
    """Get Layer 1 statistics (reviews scraped and filters)"""
    reviews_file = os.path.join(settings.REVIEWS_DIR, f"reviews_{week_key}.json")
    raw_reviews_file = os.path.join(settings.RAW_REVIEWS_DIR, f"raw_reviews_{week_key}.json")
    
    stats = {
        "total_scraped": 0,
        "total_processed": 0,
        "filtered_emoji": 0,
        "filtered_pii": 0,
        "filtered_non_english": 0,
        "filtered_too_short": 0,
        "platform_breakdown": {"app_store": 0, "play_store": 0}
    }
    
    # Get raw reviews count
    raw_data = load_json_file(raw_reviews_file)
    if raw_data:
        # Handle both formats: list of reviews or dict with 'reviews' key
        if isinstance(raw_data, list):
            stats["total_scraped"] = len(raw_data)
        else:
            stats["total_scraped"] = raw_data.get("total_reviews", len(raw_data.get("reviews", [])))
    
    # Get processed reviews
    reviews_data = load_json_file(reviews_file)
    if reviews_data:
        # Handle both formats
        if isinstance(reviews_data, list):
            reviews = reviews_data
        else:
            reviews = reviews_data.get("reviews", [])
        
        stats["total_processed"] = len(reviews)
        
        # Platform breakdown
        for review in reviews:
            platform = review.get("platform", "unknown")
            if platform in stats["platform_breakdown"]:
                stats["platform_breakdown"][platform] += 1
        
        # Calculate filtered (approximate - actual counts would need to be stored)
        if stats["total_scraped"] > 0:
            stats["filtered_total"] = stats["total_scraped"] - stats["total_processed"]
        else:
            # If no raw data, we can't calculate filtered count
            stats["filtered_total"] = None
    
    return stats


def get_layer2_stats(week_key: str) -> Dict[str, Any]:
    """Get Layer 2 statistics (themes and counts)"""
    themes_file = os.path.join(settings.THEMES_DIR, f"themes_{week_key}.json")
    themes_data = load_json_file(themes_file)
    
    if not themes_data:
        return {"theme_counts": {}, "total_reviews": 0}
    
    return {
        "theme_counts": themes_data.get("theme_counts", {}),
        "total_reviews": themes_data.get("total_reviews", 0),
        "top_themes": themes_data.get("top_themes", [])
    }


def get_layer3_data(week_key: str) -> Dict[str, Any]:
    """Get Layer 3 data (pulse with top themes, quotes, actions)"""
    pulse_file = os.path.join(settings.PULSES_DIR, f"pulse_{week_key}.json")
    pulse_data = load_json_file(pulse_file)
    
    if not pulse_data:
        return {}
    
    return {
        "pulse": pulse_data.get("pulse", {}),
        "top_3_themes": pulse_data.get("top_3_themes", []),
        "week_start": pulse_data.get("week_start_date", ""),
        "week_end": pulse_data.get("week_end_date", ""),
        "total_reviews": pulse_data.get("total_reviews", 0)
    }


def get_layer4_status(week_key: str) -> Dict[str, Any]:
    """Get Layer 4 status (email generation and sending)"""
    email_file = os.path.join(settings.EMAILS_DIR, f"email_{week_key}.json")
    email_data = load_json_file(email_file)
    
    if not email_data:
        return {"status": "not_generated", "exists": False}
    
    return {
        "status": "generated",
        "exists": True,
        "subject": email_data.get("subject", ""),
        "word_count": email_data.get("word_count", 0),
        "pii_detected": email_data.get("pii_count", 0),
        "generated_at": email_data.get("generated_at", "")
    }


def pulse_to_markdown(pulse_data: Dict[str, Any], week_start: str, week_end: str) -> str:
    """Convert pulse data to Markdown format"""
    pulse = pulse_data.get("pulse", {})
    
    md = f"""# Weekly Product Pulse

**Week:** {week_start} to {week_end}

## {pulse.get('title', 'Weekly Pulse')}

### Overview

{pulse.get('overview', '')}

### Top Themes

"""
    
    for theme in pulse.get('themes', []):
        md += f"#### {theme.get('name', 'Unknown')}\n\n"
        md += f"{theme.get('summary', '')}\n\n"
    
    md += "### User Quotes\n\n"
    for quote in pulse.get('quotes', []):
        md += f"- {quote}\n"
    
    md += "\n### Action Items\n\n"
    for action in pulse.get('actions', []):
        md += f"- {action}\n"
    
    return md


def check_if_first_run() -> bool:
    """Check if this is the first run (no data exists)"""
    pulses_dir = os.path.join(settings.DATA_DIR, "pulses")
    if not os.path.exists(pulses_dir):
        return True
    
    pulse_files = [
        f for f in os.listdir(pulses_dir)
        if f.startswith('pulse_') and f.endswith('.json')
    ]
    return len(pulse_files) == 0


def run_pipeline_with_progress():
    """Run the full pipeline with progress tracking"""
    # Create a placeholder for progress bar
    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    
    results = {
        "layer1": {"success": False, "reviews_count": 0, "error": None},
        "layer2": {"success": False, "weeks_processed": 0, "error": None},
        "layer3": {"success": False, "pulses_generated": 0, "error": None},
        "layer4": {"success": False, "emails_generated": 0, "error": None}
    }
    
    try:
        # Layer 1: Import Reviews
        with status_placeholder.container():
            progress_placeholder.progress(0, text="🔵 **Layer 1: Importing Reviews** (0%)")
            with st.status("🔵 **Layer 1: Importing Reviews** - Fetching reviews from App Store and Play Store...", expanded=True) as status:
                st.write("📥 Fetching reviews from stores...")
                st.write("🔍 Validating and filtering reviews...")
                st.write("💾 Storing reviews by week...")
                
                try:
                    reviews = import_reviews()
                    results["layer1"]["success"] = True
                    results["layer1"]["reviews_count"] = len(reviews)
                    status.update(label="✅ **Layer 1 Complete** - Reviews imported successfully", state="complete")
                    st.success(f"✅ Imported {len(reviews)} reviews")
                except Exception as e:
                    results["layer1"]["error"] = str(e)
                    status.update(label="❌ **Layer 1 Failed**", state="error")
                    st.error(f"Error: {str(e)}")
                    return results
        
        progress_placeholder.progress(0.25, text="🟢 **Layer 2: Theme Extraction** (25%)")
        
        # Layer 2: Theme Classification
        force_regenerate = st.session_state.get('force_regenerate', False)
        with status_placeholder.container():
            status_msg = "🟢 **Layer 2: Theme Extraction** - Classifying reviews into themes..."
            if not force_regenerate:
                status_msg += " (Skipping existing themes)"
            with st.status(status_msg, expanded=True) as status:
                st.write("🤖 Using AI to classify reviews...")
                st.write("📊 Grouping reviews by theme...")
                if not force_regenerate:
                    st.write("ℹ️ Will skip weeks that already have themes")
                st.write("⏳ This may take a few minutes...")
                
                try:
                    theme_results = classify_all_reviews(force_regenerate=force_regenerate)
                    results["layer2"]["success"] = True
                    results["layer2"]["weeks_processed"] = len(theme_results)
                    skipped = len([r for r in theme_results if r.get("skipped", False)])
                    if skipped > 0:
                        status.update(label=f"✅ **Layer 2 Complete** - Processed {len(theme_results)} weeks ({skipped} skipped)", state="complete")
                        st.success(f"✅ Processed {len(theme_results)} weeks ({skipped} skipped, {len(theme_results)-skipped} newly classified)")
                    else:
                        status.update(label="✅ **Layer 2 Complete** - Themes extracted successfully", state="complete")
                        st.success(f"✅ Processed {len(theme_results)} weeks")
                except Exception as e:
                    results["layer2"]["error"] = str(e)
                    status.update(label="❌ **Layer 2 Failed**", state="error")
                    st.error(f"Error: {str(e)}")
                    return results
        
        progress_placeholder.progress(0.50, text="🟡 **Layer 3: Content Generation** (50%)")
        
        # Layer 3: Pulse Generation
        with status_placeholder.container():
            status_msg = "🟡 **Layer 3: Content Generation** - Generating weekly summaries..."
            if not force_regenerate:
                status_msg += " (Skipping existing pulses)"
            with st.status(status_msg, expanded=True) as status:
                st.write("📝 Summarizing themes...")
                st.write("✍️ Creating pulse documents...")
                st.write("🎯 Extracting quotes and action items...")
                if not force_regenerate:
                    st.write("ℹ️ Will skip weeks that already have pulses")
                
                try:
                    pulse_results = generate_all_pulses(force_regenerate=force_regenerate)
                    successful_pulses = len([r for r in pulse_results if 'error' not in r])
                    results["layer3"]["success"] = True
                    results["layer3"]["pulses_generated"] = successful_pulses
                    status.update(label="✅ **Layer 3 Complete** - Pulses generated successfully", state="complete")
                    st.success(f"✅ Generated {successful_pulses} pulses")
                except Exception as e:
                    results["layer3"]["error"] = str(e)
                    status.update(label="❌ **Layer 3 Failed**", state="error")
                    st.error(f"Error: {str(e)}")
                    return results
        
        progress_placeholder.progress(0.75, text="🔴 **Layer 4: Distribution** (75%)")
        
        # Layer 4: Email Generation
        with status_placeholder.container():
            with st.status("🔴 **Layer 4: Distribution** - Generating email templates...", expanded=True) as status:
                st.write("📧 Drafting email content...")
                st.write("🔒 Checking for PII...")
                st.write("💾 Saving email templates...")
                
                try:
                    from layer_4_distribution.generate_email import generate_and_send_all_emails
                    email_results = generate_and_send_all_emails(send=False)
                    successful_emails = len([r for r in email_results if r.get('success')])
                    results["layer4"]["success"] = True
                    results["layer4"]["emails_generated"] = successful_emails
                    status.update(label="✅ **Layer 4 Complete** - Emails generated successfully", state="complete")
                    st.success(f"✅ Generated {successful_emails} email templates")
                except Exception as e:
                    results["layer4"]["error"] = str(e)
                    status.update(label="❌ **Layer 4 Failed**", state="error")
                    st.error(f"Error: {str(e)}")
                    return results
        
        progress_placeholder.progress(1.0, text="✅ **Pipeline Complete** (100%)")
        
        # Success message
        st.balloons()
        st.success("🎉 **Pipeline completed successfully!**")
        
        # Clear placeholders after a moment
        time.sleep(2)
        progress_placeholder.empty()
        status_placeholder.empty()
        
    except Exception as e:
        st.error(f"❌ Pipeline failed with error: {str(e)}")
        logger.error(f"Pipeline error: {e}", exc_info=True)
        progress_placeholder.empty()
        status_placeholder.empty()
    
    return results


def main():
    """Main Streamlit app"""
    
    # Header
    st.markdown('<h1 class="main-header">📊 App Review Insights Dashboard</h1>', unsafe_allow_html=True)
    
    # Check if first run
    is_first_run = check_if_first_run()
    
    # Pipeline execution section
    if is_first_run:
        st.warning("""
        🚀 **First Time Setup Detected**
        
        No data found in the system. Click the **"Run Full Pipeline"** button in the sidebar to:
        1. Import reviews from App Store and Play Store
        2. Classify reviews into themes
        3. Generate weekly summaries
        4. Create email templates
        
        This process may take several minutes depending on the number of reviews.
        """)
    
    # Pipeline control in sidebar
    st.sidebar.header("⚙️ Pipeline Control")
    
    # Force regenerate option
    force_regenerate = st.sidebar.checkbox(
        "🔄 Force Regenerate All",
        value=False,
        help="If checked, will regenerate all data even if it already exists. Unchecked will skip existing data."
    )
    
    if st.sidebar.button("🚀 Run Full Pipeline", type="primary", width='stretch'):
        st.session_state['run_pipeline'] = True
        st.session_state['force_regenerate'] = force_regenerate
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**📅 Scheduled Runs:**")
    st.sidebar.markdown("Pipeline runs automatically every Monday at 9:00 AM (configured in `scheduler.py`)")
    st.sidebar.markdown("---")
    
    # Show pipeline status if running
    if st.session_state.get('pipeline_running', False):
        st.info("⏳ Pipeline is currently running... Please wait.")
    
    # Run pipeline if triggered
    if st.session_state.get('run_pipeline', False):
        st.session_state['run_pipeline'] = False
        st.session_state['pipeline_running'] = True
        
        # Show pipeline execution
        st.markdown("---")
        st.header("🚀 Running Pipeline")
        st.markdown("The pipeline is processing all 4 layers. This may take several minutes...")
        
        results = run_pipeline_with_progress()
        
        st.session_state['pipeline_running'] = False
        
        # Show summary
        if all([r.get("success", False) for r in results.values()]):
            st.markdown("---")
            st.subheader("📊 Pipeline Summary")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Layer 1", f"{results['layer1']['reviews_count']} reviews", help="Reviews imported and processed")
            with col2:
                st.metric("Layer 2", f"{results['layer2']['weeks_processed']} weeks", help="Weeks with themes extracted")
            with col3:
                st.metric("Layer 3", f"{results['layer3']['pulses_generated']} pulses", help="Weekly summaries generated")
            with col4:
                st.metric("Layer 4", f"{results['layer4']['emails_generated']} emails", help="Email templates created")
            
            st.success("✅ Pipeline completed successfully! Data is now available in the dashboard.")
            st.info("💡 **Tip:** Use the tabs above to view statistics, preview pulses, and manage emails.")
            st.info("📅 **Note:** The pipeline will run automatically on the next scheduled time (Monday). Use the 'Run Full Pipeline' button to run manually anytime.")
    
    # Sidebar for week selection
    st.sidebar.header("📅 Week Selection")
    available_weeks = get_available_weeks()
    
    if not available_weeks:
        if not is_first_run:
            st.warning("⚠️ No pulse data available. Run the pipeline to generate data.")
        st.stop()
    
    selected_week = st.sidebar.selectbox(
        "Select Week",
        available_weeks,
        index=0
    )
    
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Selected Week:** {selected_week}")
    
    # Main content
    tab1, tab2, tab3 = st.tabs(["📈 Statistics", "📄 Pulse Preview", "📧 Email Management"])
    
    # ============================================================
    # TAB 1: Statistics
    # ============================================================
    with tab1:
        st.header("Layer Statistics")
        
        # Layer 1: Data Import
        st.subheader("🔵 Layer 1: Data Import")
        layer1_stats = get_layer1_stats(selected_week)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Scraped", layer1_stats.get("total_scraped", 0))
        with col2:
            st.metric("Processed", layer1_stats.get("total_processed", 0))
        with col3:
            filtered = layer1_stats.get("filtered_total")
            if filtered is not None:
                st.metric("Filtered Out", filtered)
            else:
                st.metric("Filtered Out", "N/A", help="Raw review data not available")
        with col4:
            if layer1_stats.get("total_scraped", 0) > 0:
                success_rate = (layer1_stats.get("total_processed", 0) / layer1_stats.get("total_scraped", 1)) * 100
                st.metric("Success Rate", f"{success_rate:.1f}%")
        
        # Platform breakdown
        platform_data = layer1_stats.get("platform_breakdown", {})
        if platform_data:
            st.markdown("**Platform Breakdown:**")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Play Store", platform_data.get("play_store", 0))
            with col2:
                st.metric("App Store", platform_data.get("app_store", 0))
        
        st.markdown("---")
        
        # Layer 2: Theme Extraction
        st.subheader("🟢 Layer 2: Theme Extraction")
        layer2_stats = get_layer2_stats(selected_week)
        
        theme_counts = layer2_stats.get("theme_counts", {})
        if theme_counts:
            # Metrics
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Classified", layer2_stats.get("total_reviews", 0))
            with col2:
                st.metric("Number of Themes", len(theme_counts))
            
            # Theme distribution chart
            if theme_counts:
                df_themes = pd.DataFrame([
                    {"Theme": theme, "Count": count}
                    for theme, count in theme_counts.items()
                ])
                df_themes = df_themes.sort_values("Count", ascending=False)
                
                fig = px.bar(
                    df_themes,
                    x="Theme",
                    y="Count",
                    title="Reviews per Theme",
                    color="Count",
                    color_continuous_scale="Blues"
                )
                fig.update_layout(height=400, xaxis_tickangle=-45)
                st.plotly_chart(fig, width='stretch')
                
                # Theme counts table
                st.markdown("**Theme Distribution:**")
                st.dataframe(df_themes, width='stretch', hide_index=True)
        else:
            st.info("No theme data available for this week.")
        
        st.markdown("---")
        
        # Layer 3: Content Generation
        st.subheader("🟡 Layer 3: Content Generation")
        layer3_data = get_layer3_data(selected_week)
        
        if layer3_data:
            pulse = layer3_data.get("pulse", {})
            top_themes = layer3_data.get("top_3_themes", [])
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Reviews", layer3_data.get("total_reviews", 0))
            with col2:
                word_count = len(str(pulse).split()) if pulse else 0
                st.metric("Pulse Word Count", word_count)
            
            # Top 3 Themes
            if top_themes:
                st.markdown("**Top 3 Themes:**")
                for idx, theme_item in enumerate(top_themes[:3], 1):
                    if isinstance(theme_item, dict):
                        theme_name = theme_item.get("theme", "Unknown")
                        theme_count = theme_item.get("count", 0)
                    else:
                        theme_name, theme_count = theme_item
                    
                    st.markdown(f"{idx}. **{theme_name}** - {theme_count} reviews")
            
            # Top quotes from pulse
            quotes = pulse.get("quotes", [])
            if quotes:
                st.markdown("**Top Quotes:**")
                for quote in quotes[:3]:
                    st.markdown(f"- {quote}")
        else:
            st.info("No pulse data available for this week.")
        
        st.markdown("---")
        
        # Layer 4: Distribution
        st.subheader("🔴 Layer 4: Distribution")
        layer4_status = get_layer4_status(selected_week)
        
        if layer4_status.get("exists"):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Status", "✅ Generated")
            with col2:
                st.metric("Word Count", layer4_status.get("word_count", 0))
            with col3:
                pii_count = layer4_status.get("pii_detected", 0)
                st.metric("PII Detected", pii_count, delta=None if pii_count == 0 else "⚠️")
            
            st.markdown(f"**Subject:** {layer4_status.get('subject', 'N/A')}")
            if layer4_status.get("generated_at"):
                gen_time = layer4_status.get("generated_at", "")
                st.markdown(f"**Generated At:** {gen_time}")
        else:
            st.warning("Email not generated yet. Generate it in the Email Management tab.")
    
    # ============================================================
    # TAB 2: Pulse Preview
    # ============================================================
    with tab2:
        st.header("Weekly Pulse Preview")
        
        layer3_data = get_layer3_data(selected_week)
        
        if not layer3_data:
            st.error("No pulse data available for this week.")
        else:
            pulse = layer3_data.get("pulse", {})
            week_start = layer3_data.get("week_start", "")
            week_end = layer3_data.get("week_end", "")
            
            # Display pulse
            st.markdown(f"### {pulse.get('title', 'Weekly Pulse')}")
            st.markdown(f"**Week:** {week_start} to {week_end}")
            st.markdown("---")
            
            st.markdown("#### Overview")
            st.markdown(pulse.get('overview', ''))
            
            st.markdown("#### Themes")
            for theme in pulse.get('themes', []):
                st.markdown(f"**{theme.get('name', 'Unknown')}**")
                st.markdown(theme.get('summary', ''))
            
            st.markdown("#### User Quotes")
            for quote in pulse.get('quotes', []):
                st.markdown(f"- {quote}")
            
            st.markdown("#### Action Items")
            for action in pulse.get('actions', []):
                st.markdown(f"- {action}")
            
            # Download button
            st.markdown("---")
            markdown_content = pulse_to_markdown(layer3_data, week_start, week_end)
            
            st.download_button(
                label="📥 Download Pulse as Markdown",
                data=markdown_content,
                file_name=f"pulse_{selected_week}.md",
                mime="text/markdown"
            )
    
    # ============================================================
    # TAB 3: Email Management
    # ============================================================
    with tab3:
        st.header("Email Management")
        
        layer3_data = get_layer3_data(selected_week)
        layer4_status = get_layer4_status(selected_week)
        
        if not layer3_data:
            st.error("Cannot generate email: No pulse data available for this week.")
            st.stop()
        
        # Email generation status
        if layer4_status.get("exists"):
            st.success("✅ Email template already generated")
            st.markdown(f"**Subject:** {layer4_status.get('subject', 'N/A')}")
            st.markdown(f"**Word Count:** {layer4_status.get('word_count', 0)}")
        else:
            st.info("Email template not generated yet. Click 'Generate Email' to create it.")
            
            if st.button("🔄 Generate Email Template", type="primary"):
                with st.spinner("Generating email template..."):
                    try:
                        generator = EmailGenerator()
                        result = generator.generate_email_preview(selected_week, regenerate=False)
                        
                        if result.get("success"):
                            st.success("✅ Email template generated successfully!")
                            st.rerun()
                        else:
                            st.error(f"❌ Error: {result.get('error', 'Unknown error')}")
                    except Exception as e:
                        st.error(f"❌ Error generating email: {str(e)}")
        
        st.markdown("---")
        
        # Email sending section
        st.subheader("Send Email")
        
        # Get recipient email from input
        recipient_email = st.text_input(
            "Recipient Email Address",
            value=os.getenv("TO_EMAIL", ""),
            placeholder="recipient@example.com"
        )
        
        col1, col2 = st.columns([1, 3])
        with col1:
            send_button = st.button("📧 Send Email", type="primary", disabled=not layer4_status.get("exists"))
        
        if send_button:
            if not recipient_email or "@" not in recipient_email:
                st.error("Please enter a valid email address")
            else:
                with st.spinner("Sending email..."):
                    try:
                        # Load email template
                        generator = EmailGenerator()
                        email_template = generator.load_email_template(selected_week)
                        
                        if not email_template:
                            st.error("Email template not found. Please generate it first.")
                        else:
                            # Send email
                            sender = EmailSender()
                            result = sender.send_email(
                                subject=email_template.get("subject", ""),
                                body=email_template.get("email_body", ""),
                                to_email=recipient_email
                            )
                            
                            if result.get("success"):
                                st.success(f"✅ Email sent successfully to {recipient_email}!")
                                st.balloons()
                            else:
                                st.error(f"❌ Failed to send email: {result.get('error', 'Unknown error')}")
                    except Exception as e:
                        st.error(f"❌ Error sending email: {str(e)}")
        
        # Email preview
        if layer4_status.get("exists"):
            st.markdown("---")
            st.subheader("Email Preview")
            
            email_template = load_json_file(
                os.path.join(settings.EMAILS_DIR, f"email_{selected_week}.json")
            )
            
            if email_template:
                with st.expander("View Email Content"):
                    st.markdown(f"**Subject:** {email_template.get('subject', '')}")
                    st.markdown("**Body:**")
                    st.text_area(
                        "Email Body",
                        value=email_template.get("email_body", ""),
                        height=300,
                        disabled=True
                    )


if __name__ == "__main__":
    main()

