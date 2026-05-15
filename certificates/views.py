from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import CertificateTemplate, Certificate
from .forms import CertificateTemplateForm
from events.models import Event
from registrations.models import Registration
from config.task_utils import trigger_background_tasks

@login_required
def certificate_list(request):
    if request.user.role == 'participant':
        # Participants see their own certificates
        certificates = Certificate.objects.filter(registration__user=request.user, status='completed')
        return render(request, 'certificates/certificate_list.html', {
            'user_certificates': certificates,
            'is_manager': False
        })
    else:
        # Managers see templates
        templates = CertificateTemplate.objects.all()
        return render(request, 'certificates/certificate_list.html', {
            'templates': templates,
            'templates_count': templates.count(),
            'certs_issued': Certificate.objects.filter(status='completed').count(),
            'is_manager': True
        })

@login_required
def issue_bulk_certificates(request, event_id):
    """
    Trigger bulk certificate generation for an event.
    """
    event = get_object_or_404(Event, id=event_id)
    
    # Get all eligible registrations that don't have a certificate yet
    eligible_regs = Registration.objects.filter(
        event=event, 
        status=Registration.Status.CONFIRMED,
        is_eligible_for_certificate=True
    ).exclude(certificates__isnull=False)
    
    if not eligible_regs.exists():
        # Check if all participants should get certs regardless of eligibility calculation
        if event.certificate_eligible_all:
             eligible_regs = Registration.objects.filter(
                event=event, 
                status=Registration.Status.CONFIRMED
            ).exclude(certificates__isnull=False)

    if not eligible_regs.exists():
        messages.info(request, "No new eligible participants found for certificate issuance.")
        return redirect('events:event_detail', pk=event.id)
        
    # Get the default template for this event
    template = event.certificate_templates.filter(is_active=True).first()
    if not template:
        messages.error(request, "No active certificate template found for this event. Please create one first.")
        return redirect('certificates:certificate_list')

    # Create Certificate records in PENDING state
    count = 0
    for reg in eligible_regs:
        Certificate.objects.get_or_create(
            registration=reg,
            template=template,
            defaults={
                'issued_by': request.user,
                'status': Certificate.Status.PENDING
            }
        )
        count += 1
        
    messages.success(request, f"Successfully queued {count} certificates for generation.")
    trigger_background_tasks() # Automatically start PDF generation
    return redirect('events:event_detail', pk=event.id)

@login_required
def template_create(request):
    if request.method == 'POST':
        form = CertificateTemplateForm(request.POST, request.FILES)
        if form.is_valid():
            template = form.save()
            messages.success(request, f"Template '{template.name}' created successfully!")
            return redirect('certificates:certificate_list')
    else:
        form = CertificateTemplateForm()
    
    # Provide a default JSON for convenience
    default_json = '{"fields": [{"type": "participant_name", "x": 500, "y": 500, "font": "Helvetica-Bold", "size": 36, "align": "center"}]}'
    
    return render(request, 'certificates/template_form.html', {
        'form': form,
        'title': 'Create Certificate Template',
        'default_json': default_json
    })

@login_required
def template_update(request, pk):
    template = get_object_or_404(CertificateTemplate, id=pk)
    if request.method == 'POST':
        form = CertificateTemplateForm(request.POST, request.FILES, instance=template)
        if form.is_valid():
            form.save()
            messages.success(request, f"Template '{template.name}' updated successfully!")
            return redirect('certificates:certificate_list')
    else:
        form = CertificateTemplateForm(instance=template)
    
    return render(request, 'certificates/template_form.html', {
        'form': form,
        'title': 'Edit Certificate Template',
        'template': template
    })
