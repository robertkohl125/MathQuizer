__author__ = 'robertkohl125@gmail.com (Robert Kohl)'

import httplib
import endpoints
from protorpc import messages
from google.appengine.ext import ndb
from google.appengine.ext.ndb import msgprop


# Define the Profile Kind
class Profile(ndb.Model):
    """Profile -- User profile object"""
    user_id             = ndb.StringProperty()
    displayName         = ndb.StringProperty()
    mainEmail           = ndb.StringProperty()
    studentKeys             = ndb.StringProperty(repeated=True)


# Define the Student Kind
class Student(ndb.Model):
    """Profile -- User profile object"""
    user_id             = ndb.StringProperty()
    displayName         = ndb.StringProperty()
    mainEmail           = ndb.StringProperty()
    score               = ndb.StringProperty()


class QuizForm(messages.Message):
    """QuizForm -- Query inbound form message"""
    integer1 = messages.IntegerField(1)
    integer2 = messages.IntegerField(2)    
    operator = messages.StringField(3)
    score = messages.StringField(4)


class ProfileMiniForm(messages.Message):
    """ProfileMiniForm -- update Profile form message"""
    displayName = messages.StringField(1)


class ProfileForm(messages.Message):
    """ProfileForm -- Profile outbound form message"""
    displayName = messages.StringField(1)
    mainEmail = messages.StringField(2)
    studentKeys = messages.StringField(3, repeated=True)