from django.shortcuts import render

def home(request):
    """
    Django home page with link to launch Flask app
    """
    return render(request, 'home.html')
