"""
Quick launcher for Streamlit dashboard
"""
import subprocess
import sys
import os

def main():
    """Launch Streamlit dashboard"""
    # Ensure we're in the right directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Check if streamlit is installed
    try:
        import streamlit
    except ImportError:
        print("Streamlit is not installed. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit", "plotly"])
    
    # Run streamlit
    print("Starting Streamlit dashboard...")
    print("Dashboard will open in your browser at http://localhost:8501")
    subprocess.run([sys.executable, "-m", "streamlit", "run", "streamlit_app.py"])

if __name__ == "__main__":
    main()

