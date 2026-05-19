from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User

class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={
        'class': 'appearance-none block w-full px-3 py-2 border rounded-xl shadow-sm focus:outline-none focus:ring-indigo-500 sm:text-sm',
        'placeholder': 'Neural ID (Email)'
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'appearance-none block w-full px-3 py-2 border rounded-xl shadow-sm focus:outline-none focus:ring-indigo-500 sm:text-sm',
        'placeholder': 'Access Key (Password)'
    }))

class SignupForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name')
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({
                'class': 'appearance-none block w-full px-3 py-2 border rounded-xl shadow-sm focus:outline-none focus:ring-indigo-500 sm:text-sm'
            })
