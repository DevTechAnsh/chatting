from django import forms
from django.utils.translation import gettext_lazy as _

from patient.models import Patient
from utils.forms import DictErrorMixin
from .models import ChatOpinionConversation, Complaint


class CaseDetailPatientDetailForm(DictErrorMixin, forms.ModelForm):

    speciality = forms.ChoiceField(label=_('Choose Department'))
    patient = forms.ModelChoiceField(label=_('Patient'),
                                     queryset=Patient.objects.none())

    class Meta:
        model = Patient
        fields = ['speciality', 'patient']

    def __init__(self, *args, **kwargs):
        doctor = kwargs.pop('doctor', None)
        request = kwargs.pop('request', None)
        super(CaseDetailPatientDetailForm, self).__init__(*args, **kwargs)
        if doctor:
            choices = doctor.get_speciality_qs()
            temp_choices = ((choice.slug, choice.name) for choice in choices)
            self.fields['speciality'].choices = temp_choices
        if request:
            user = request.user
            if user:
                self.fields['patient'].queryset = Patient.objects.filter(
                    parent=user, is_deleted=False)


class ConversationForm(DictErrorMixin, forms.ModelForm):

    class Meta:
        model = ChatOpinionConversation
        fields = '__all__'
        exclude = ['doctor_attachments', 'reply_count', 'patient_attachments']

    def clean(self):
        cleaned_data = super(ConversationForm, self).clean()
        booking = cleaned_data['booking']
        is_doctor_message = cleaned_data.get('is_doctor_message', False)

        if booking.is_completed:
            raise forms.ValidationError(
                {'message': [_('This booking is closed by doctor')]})

        if not is_doctor_message and not booking.can_patient_reply():
            raise forms.ValidationError({
                'message': [_('Maximum Replies limit is 3')]
            })
        return cleaned_data


class ComplaintForm(DictErrorMixin, forms.ModelForm):

    class Meta:
        model = Complaint
        fields = ['description', 'booking', 'user', 'type']
        widgets = {
            'user': forms.HiddenInput(),
            'type': forms.HiddenInput()
        }
