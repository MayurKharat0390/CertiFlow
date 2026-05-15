from .models import Organization, Membership

def current_organization(request):
    """
    Context processor to add the current organization to the template context.
    """
    if not request.user.is_authenticated:
        return {}
    
    # Try to get organization from session or user's primary membership
    org_id = request.session.get('current_org_id')
    
    if org_id:
        try:
            organization = Organization.objects.get(id=org_id)
            return {'current_org': organization}
        except Organization.DoesNotExist:
            pass
            
    # Fallback to the first organization the user is a member of
    membership = request.user.memberships.filter(is_active=True).first()
    if membership:
        request.session['current_org_id'] = str(membership.organization.id)
        return {'current_org': membership.organization}
        
    return {}
