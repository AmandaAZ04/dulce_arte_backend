from django.shortcuts import render,redirect
from django.views.decorators.csrf import ensure_csrf_cookie
from django.conf import settings
@ensure_csrf_cookie
def inicio(request):
    if not request.user.is_authenticated: return redirect('/cuenta/')
    return render(request,'inicio.html',{'direccion':settings.LOCAL_ADDRESS})
@ensure_csrf_cookie
def equipo(request):
    if not request.user.is_authenticated: return redirect('/cuenta/?equipo=1')
    if not request.user.is_staff: return render(request,'sin_acceso.html',status=403)
    return render(request,'equipo.html',{'direccion':settings.LOCAL_ADDRESS})
@ensure_csrf_cookie
def cuenta(request):
    if request.user.is_authenticated:
        if request.user.is_staff: return redirect('/equipo/')
        producto=request.GET.get('producto')
        return redirect('/'+('?producto='+producto if producto and producto.isdigit() else ''))
    return render(request,'cuenta.html')
@ensure_csrf_cookie
def mis_pedidos(request):
    if not request.user.is_authenticated: return redirect('/cuenta/')
    return render(request,'pedidos.html',{'direccion':settings.LOCAL_ADDRESS})
def seguimiento(request,token):
    r=render(request,'seguimiento.html',{'token':str(token),'direccion':settings.LOCAL_ADDRESS})
    r['Referrer-Policy']='no-referrer';r['Cache-Control']='no-store';return r
