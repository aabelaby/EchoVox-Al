from django.http import HttpResponse, HttpResponseRedirect
import subprocess
import sys
from pathlib import Path

def launch_app(request):
    """
    Django view that launches the Flask app directly and redirects to it
    """
    # Get the parent directory (where app.py is located)
    parent_dir = Path(__file__).resolve().parent.parent.parent
    
    # Path to app.py
    flask_app_path = parent_dir / "app.py"
    
    if not flask_app_path.exists():
        return HttpResponse("Flask app not found at app.py", status=500)
    
    try:
        # Start Flask app in a subprocess
        subprocess.Popen([
            sys.executable, 
            str(flask_app_path)
        ], cwd=str(parent_dir))
        
        # Give the Flask app a moment to start up
        import time
        time.sleep(2)
        
        # Redirect to the Flask app
        return HttpResponseRedirect("http://127.0.0.1:5000")
        
    except Exception as e:
        return HttpResponse(
            f"Failed to start Flask app: {str(e)}", 
            status=500,
            content_type="text/plain"
        )
