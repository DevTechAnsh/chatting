from modeltranslation.translator import TranslationOptions, translator

from Chat_opinion.models import ChatOpinionQuestion


class ChatOpinionQuestionTranslation(TranslationOptions):
    fields = ('label', 'help_text',)


translator.register(ChatOpinionQuestion, ChatOpinionQuestionTranslation)

