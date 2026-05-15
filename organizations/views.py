from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Organization

@login_required
def organization_list(request):
    if request.user.role == 'participant':
        # Participants only see organizations they are members of
        organizations = Organization.objects.filter(memberships__user=request.user)
        is_admin = False
    else:
        organizations = Organization.objects.all()
        is_admin = request.user.is_superuser or request.user.role == 'org_admin'
        
    return render(request, 'organizations/org_list.html', {
        'organizations': organizations,
        'is_admin': is_admin
    })

@login_required
def organization_detail(request, slug):
    organization = get_object_or_404(Organization, slug=slug)
    
    # Security check: only members (or superusers) can see the detail/manage page
    if not request.user.is_superuser and not organization.memberships.filter(user=request.user).exists():
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    events = organization.events.all().order_by('-start_datetime')
    memberships = organization.memberships.all()
    return render(request, 'organizations/org_detail.html', {
        'organization': organization,
        'events': events,
        'memberships': memberships,
        'is_admin': request.user.is_superuser or organization.memberships.filter(user=request.user, role='admin').exists()
    })
