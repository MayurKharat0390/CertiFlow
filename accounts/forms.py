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

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            'first_name', 'last_name', 'phone', 
            'institution', 'department', 'year_of_study', 
            'github_url', 'linkedin_url', 'portfolio_url'
        )
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({
                'class': 'appearance-none block w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm'
            })
