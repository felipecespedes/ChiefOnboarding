import boto3
from botocore.config import Config
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import IsAuthenticatedOrReadOnly, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Organization, Tag, WelcomeMessage
from misc.models import File
from .serializers import BaseOrganizationSerializer, DetailOrganizationSerializer, \
    WelcomeMessageSerializer, ExportSerializer
from misc.serializers import FileSerializer
from users.permissions import NewHirePermission, AdminPermission
from django.core import management


def home(request):
    return render(request, 'index.html')


class OrgView(APIView):
    permission_classes = (IsAuthenticatedOrReadOnly,)

    def get(self, request):
        org = BaseOrganizationSerializer(Organization.object.get())
        return Response(org.data)


class OrgDetailView(APIView):

    def get(self, request):
        org = DetailOrganizationSerializer(Organization.object.get())
        return Response(org.data)

    def patch(self, request):
        serializer = DetailOrganizationSerializer(Organization.object.get(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class WelcomeMessageView(APIView):
    permission_classes = (IsAuthenticatedOrReadOnly,)

    def get(self, request):
        welcome_messages = WelcomeMessage.objects.all()
        serializer = WelcomeMessageSerializer(welcome_messages, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = WelcomeMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        welcome_message = WelcomeMessage.objects.get(language=serializer.data['language'], message_type=serializer.data['message_type'])
        welcome_message.message = serializer.data['message']
        welcome_message.save()
        return Response(serializer.data)


class TagView(APIView):
    permission_classes = (IsAuthenticatedOrReadOnly,)

    def get(self, request):
        tags = [i.name for i in Tag.objects.all()]
        return Response(tags)


class CSRFTokenView(APIView):
    permission_classes = (AllowAny,)

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return HttpResponse()


class FileView(APIView):
    permission_classes = (AdminPermission, NewHirePermission)

    def get(self, request, id, uuid):
        file = get_object_or_404(File, uuid=uuid, id=id)
        url = file.get_url()
        return Response(url)

    def post(self, request):
        serializer = FileSerializer(data={'name': request.data['name'], 'ext': request.data['name'].split('.')[1]})
        serializer.is_valid(raise_exception=True)
        f = serializer.save()
        key = str(f.id) + '-' + request.data['name'].split('.')[0] + '/' + request.data['name']
        f.key = key
        f.save()

        s3 = boto3.client('s3',
                          settings.AWS_REGION,
                          endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                          aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                          aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                          config=Config(signature_version='s3v4')
                          )
        url = s3.generate_presigned_url(ClientMethod='put_object', ExpiresIn=3600,
                                        Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': key})
        return Response({'url': url, 'id': f.id})

    def put(self, request, id):
        file = get_object_or_404(File, pk=id)
        file.active = True
        file.save()
        return Response(FileSerializer(file).data)

    def delete(self, request, id):
        if request.user.role == 1:
            file = get_object_or_404(File, pk=id)
            file.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class LogoView(APIView):

    def put(self, request, id):
        file = get_object_or_404(File, pk=id)
        file.active = True
        file.save()
        org = Organization.object.get()
        org.logo = file
        org.save()
        return Response(FileSerializer(file).data)


class ExportView(APIView):

    def post(self, request):
        from io import StringIO
        import json
        from django.core.files.base import ContentFile
        buf = StringIO()
        serializer = ExportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        management.call_command('dumpdata', serializer.data['export_model'], stdout=buf, natural_foreign=True)
        buf.seek(0)
        return Response(json.loads(buf.read()))

# Don't ask me how this works. I don't know either.
def convert_to_JSON(data):
    import re
    con = []
    content = data.replace('<br>', '').replace('<br/>', '')
    allowed_options = ['<ul>', '<ol>', '<h1>', '<h2>', '<h3>', '<h4>']
    if content[3:] != '</p>' and content[4:] not in allowed_options:
      content = '<p>' + content
    while len(content) != 0:
        end_char = '</p>'
        content_type = 'p'
        if content[:3] == '<p>':
            end_char = '</p>'
            content = content[3:]
            content_type = 'p'
            if content[:4] == '<ul>':
                end_char = '</ul>'
                content_type = 'ul'
                content = content[4:]
            if content[:4] == '<ol>':
                end_char = '</ol>'
                content_type = 'ol'
                content = content[4:]
        elif content[:4] == '<ul>':
            end_char = '</ul>'
            content_type = 'ul'
            content = content[4:]
        elif content[:4] == '<ol>':
            end_char = '</ol>'
            content_type = 'ol'
            content = content[4:]
        elif content[:4] == '<h1>':
            end_char = '</h1>'
            content_type = 'h1'
            content = content[4:]
        elif content[:4] == '<h2>':
            end_char = '</h2>'
            content_type = 'h2'
            content = content[4:]
        elif content[:4] == '<h3>':
            end_char = '</h3>'
            content_type = 'h3'
            content = content[4:]
        elif content[:4] == '<h4>':
            content_type = 'h4'
            end_char = '</h4>'
            content = content[4:]
        if content[:3] == '<p>':
            content = content[3:]
        parts = content.split(end_char, 1)
        json_items = []
        if end_char == '</ul>' or end_char == '</ol>':
            list_items = parts[0][4:].split('</li><li>')
            for x in list_items:
                json_items.append({ 'content': x.replace('</li>', '') })
        if len(parts) > 1:
            part = parts[0]
            content = parts[1]
        else:
            part = ''
            content = ''
        con.append({ 'type': content_type, 'items': json_items, 'content': part })
    return con


class ImportView(APIView):

    def post(self, request):
        from misc.models import Content
        from to_do.models import ToDo
        from preboarding.models import Preboarding
        from badges.models import Badge
        from users.models import User
        import json
        from sequences.models import ExternalMessage, Sequence, PendingAdminTask, Condition
        data = request.data['records']
        if 'to_do' in data:
            to_do = data['to_do']
            for i in to_do:
                content = i.pop('content')
                if i['form'] == None:
                    i['form'] = []
                to_do_obj = ToDo.objects.create(**i)
                for j in convert_to_JSON(content):
                    to_do_obj.content.add(Content.objects.create(**j))
        if 'preboarding' in data:
            preboarding = data['preboarding']
            for i in preboarding:
                content = i.pop('content')
                pre = Preboarding.objects.create(**i)
                for j in convert_to_JSON(content):
                    pre.content.add(Content.objects.create(**j))
        if 'badge' in data:
            badges = data['badge']
            for i in badges:
                content = i.pop('content')
                b = Badge.objects.create(**i)
                for j in convert_to_JSON(content):
                    b.content.add(Content.objects.create(**j))
        if 'sequences' in data:
            sequences = data['sequences']
            for i in sequences:
                seq = Sequence.objects.create(name=i['name'])
                for s in i['conditions']:
                    con = Condition.objects.create(sequence=seq, condition_type=s['condition_type'], days=s['days'])
                    for j in s['external_messages']:
                        ext = ExternalMessage.objects.create(name=j['name'], send_via=j['send_via'], person_type=j['person_type'])
                        if 'content' in j:
                            ext.content = j['content']
                        if 'content_json' in j:
                            for h in convert_to_JSON(j['content_json']):
                                ext.content_json.add(Content.objects.create(**h))
                        ext.save()
                        con.external_messages.add(ext)
                    for j in s['pending_task']:
                        pending_task = PendingAdminTask.objects.create(assigned_to=User.objects.filter(role=1).first(), name=j['name'], comment=j['comment'], option=j['option'], slack_user=j['slack_user'], email=j['slack_user'], date=j['date'], priority=j['priority'])
                        con.admin_tasks.add(pending_task)
                
        if 'colleagues' in data:
            colleagues = data['colleagues']
            for i in colleagues:
                if not User.objects.filter(email=email).exists():
                    User.objects.create(**i)

        return Response()

