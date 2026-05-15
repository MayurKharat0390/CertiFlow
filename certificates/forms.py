from django import forms
from .models import CertificateTemplate

class CertificateTemplateForm(forms.ModelForm):
    class Meta:
        model = CertificateTemplate
        fields = ['event', 'category', 'name', 'background_image', 'layout_config']
        widgets = {
            'layout_config': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Enter layout JSON...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({
                'class': 'mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm'
            })
