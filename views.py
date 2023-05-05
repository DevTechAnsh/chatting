from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.template.defaultfilters import striptags
from django.urls import reverse
from django.utils.encoding import force_text
from django.utils.translation import gettext_lazy as _
from el_pagination.views import AjaxListView
from wagtail.contrib.forms.forms import FormBuilder
from wagtail.core.models import Collection
from wagtail.documents.models import get_document_model

from booking.forms import BasketCreateForm
from booking.models import booking
from config.models import Speciality, ComplaintEmailConfig, bookingFee
from core import choices
from core.defaults import Chat_OPTION_COMPLAINT
from core.models import Service
from doctor.filters import DoctorFilter
from doctor.models import Doctor
from django.db.models import Q
from utils.file_upload import filename_to_title
from utils.mail import send_mail
from utils.views import CrispyCreateView
from .forms import CaseDetailPatientDetailForm, ConversationForm, ComplaintForm
from .models import (
    ChatOpinionQuestion, ChatOptionAnswer,
    ChatOpinionConversation
)
from .wagtail_hooks import ChatOpinionComplaintAdmin


class DoctorListingView(LoginRequiredMixin, AjaxListView):
    template_name = 'Chat_opinion/step_1.html'
    page_template = 'Chat_opinion/partial/partial_doctor_list.html'
    model = Doctor
    context_object_name = 'doctors'

    def get_queryset(self):
        queryset = super().get_queryset().active()
        queryset = queryset.filter(Chat_opinion=True, is_deleted=False).filter(
            Q(hospital__is_active=True) | Q(hospital__isnull=True))
        if self.request.GET.get('speciality', None):
            queryset = DoctorFilter(self.request.GET, queryset).qs
        return queryset

    def get_context_data(self, **kwargs):
        ctx = super(DoctorListingView, self).get_context_data(**kwargs)
        # specialities = Speciality.objects.specialities()
        specialities = Speciality.objects.specialities().filter(
            Q(doctor_specialities__isnull=False) & Q(doctor_specialities__is_deleted=False) & Q(
                doctor_specialities__user__is_active=True) & Q(doctor_specialities__Chat_opinion=True)).distinct().order_by('name')
        ctx.update({'specialities': specialities, 'step1': True})
        return ctx


class CaseDetailView(LoginRequiredMixin, CrispyCreateView):
    model = ChatOpinionQuestion
    template_name = 'Chat_opinion/step_2.html'
    fields = '__all__'
    success_message = _('Please Re-View Your Case')

    def get_context_data(self, **kwargs):
        context = super(CaseDetailView, self).get_context_data(**kwargs)
        form = FormBuilder(self.model.objects.all())
        context.update({'form': form.get_form_class()})

        slug = self.kwargs.get('slug', None)
        doctor = Doctor.objects.get(user__slug=slug)
        fees = bookingFee.get_solo().amount
        total = doctor.Chat_opinion_fees + fees
        basket_form_init = {
            'hospital': doctor.hospital,
            'doctor': doctor,
            'status': choices.NEW,
            'user': self.request.user,
            'fee': fees,
            'doctor_fees': doctor.Chat_opinion_fees,
            'total': total
        }

        patient_detail_form_init = dict()

        service_type = Service.objects.filter(slug='Chat-opinion')
        if service_type.exists():
            service_type = service_type.first()
            basket_form_init.update({'service_type': service_type})

        speciality = self.request.GET.get('speciality', None)
        if speciality:
            specialities = Speciality.objects.filter(slug=speciality)
            if specialities.exists():
                speciality = specialities.first()
                basket_form_init.update({'speciality': speciality})
                patient_detail_form_init.update(
                    {'speciality': speciality.slug})

        basket_form = BasketCreateForm(initial=basket_form_init,
                                       prefix='basket')

        patient_detail_form_init = CaseDetailPatientDetailForm(
            initial=patient_detail_form_init,
            **{'doctor': doctor, 'request': self.request}
        )

        context.update({'basket_form': basket_form, 'doctor': doctor,
                        'patient_detail_form': patient_detail_form_init,
                        'step2': True,
                        })
        return context

    def post(self, request, *args, **kwargs):
        form = FormBuilder(self.model.objects.all())
        form_class = form.get_form_class()
        form = form_class(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            basket_form = BasketCreateForm(request.POST, request.FILES,
                                           prefix='basket')
            if basket_form.is_valid():
                basket = basket_form.save()
                basket.status = choices.NEW
                if basket:
                    for key, value in form.cleaned_data.items():
                        question_instance = self.model.objects.get(
                            code=key)
                        answer_instance = ChatOptionAnswer.objects.create(
                            question=question_instance,
                            question_label=question_instance.label,
                            answer=value, basket=basket
                        )
                        basket.Chat_opinion_questions.add(
                            question_instance)

                patient_detail_form = CaseDetailPatientDetailForm(
                    request.POST, doctor=basket.doctor, request=request)
                if patient_detail_form.is_valid():
                    basket.patient = patient_detail_form.cleaned_data.get(
                        'patient', None)

                    speciality = patient_detail_form.cleaned_data.get(
                        'speciality', None)
                    if speciality:
                        specialities = Speciality.objects.filter(
                            slug=speciality)
                        if specialities.exists():
                            basket.speciality = specialities.first()
                    basket.save()

                    if request.FILES:
                        self.upload_documents(request, basket)

                    self.success_url = reverse('booking:review_basket',
                                               kwargs={'pk': basket.pk})

                    ctx = dict(success=True,
                               message=force_text(
                                   self.get_success_message()),
                               redirect_url=force_text(self.success_url))

                    return JsonResponse(ctx)
                else:
                    ChatOptionAnswer.objects.filter(
                        basket=basket).delete()
                    basket.delete()
                    data = patient_detail_form.dict_errors()
                    return JsonResponse(data=data, status=400)
            else:
                data = basket_form.dict_errors()
                return JsonResponse(data=data, status=400)
        else:
            data = self.dict_errors(form)
            return JsonResponse(data=data, status=400)

    def dict_errors(self, form, strip_tags=True):
        errors = {}
        for error in form.errors.items():
            errors[error[0]] = striptags(error[1]) if strip_tags else error[1]

        if not errors:
            errors['error_message'] = _('Check the fields for errors.')
        return errors

    def upload_documents(self, request, basket):
        user_slug = request.user.slug
        try:
            collection = Collection.objects.get(name=user_slug)
        except:
            collection = Collection(name=user_slug)
            root_collection = Collection.get_first_root_node()
            root_collection.add_child(instance=collection)

        DocumentModel = get_document_model()
        files = list()
        for file in request.FILES.getlist('attachments'):
            name = file.name
            if file and type(file) != int:
                file = DocumentModel(
                    file=file,
                    title=filename_to_title(name),
                    collection=collection,
                    uploaded_by_user=self.request.user
                )
                file.save()
                basket.attachments.add(file)


class ConversationsReplayView(LoginRequiredMixin, CrispyCreateView):
    form_class = ConversationForm
    model = ChatOpinionConversation
    template_name = 'patient/Chat_opinion_history_detail.html'
    success_message = _('Your Reply is saved.')

    def get_success_url(self):
        return reverse('patient:history_details',
                       kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        message = form.save()
        self.object = message.booking
        if self.request.FILES:
            self.upload_documents(self.request, message)

        if self.request.is_ajax():
            ctx = dict(success=True,
                       message=force_text(self.get_success_message()),
                       redirect_url=force_text(self.get_success_url()))
        return JsonResponse(data=ctx, status=200)

    def upload_documents(self, request, message):
        user_slug = self.object.patient.parent.slug
        try:
            collection = Collection.objects.get(name=user_slug)
        except:
            collection = Collection(name=user_slug)
            root_collection = Collection.get_first_root_node()
            root_collection.add_child(instance=collection)

        DocumentModel = get_document_model()
        for file in request.FILES.getlist('patient_attachments'):
            name = file.name
            if file and type(file) != int:
                file = DocumentModel(
                    file=file,
                    title=filename_to_title(name),
                    collection=collection,
                    uploaded_by_user=self.request.user
                )
                file.save()
                if message.is_doctor_message:
                    message.doctor_attachments.add(file)
                else:
                    message.patient_attachments.add(file)


class ComplaintView(LoginRequiredMixin, CrispyCreateView):
    model = booking
    form_class = ComplaintForm
    template_name = 'Chat_opinion/complaint.html'
    success_message = _('Your Complaint have been recorded successfully')
    success_url = '/'

    def get_success_url(self):
        return reverse('patient:history_details',
                       kwargs={'pk': self.object.booking.pk})

    def get_context_data(self, **kwargs):
        ctx = super(ComplaintView, self).get_context_data(**kwargs)
        ctx.update({'booking': self.object})
        return ctx

    def post_form_valid(self):
        email = ComplaintEmailConfig.get_solo().email or ''
        url = ChatOpinionComplaintAdmin().url_helper.index_url
        send_mail(slug=Chat_OPTION_COMPLAINT, to=email,
                  ctx={'complaint': self.object, 'admin_url': url},
                  request=self.request)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self.render_to_response(self.get_context_data())

    def get_initial(self):
        init = super(ComplaintView, self).get_initial()
        if self.object:
            init.update({'booking': self.object,
                         'user': self.request.user,
                         'type': choices.PATIENT
                         })
        return init
