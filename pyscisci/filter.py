# -*- coding: utf-8 -*-
"""
.. module:: all
    :synopsis: easy interface to all of pyscisci

.. moduleauthor:: Alex Gates <ajgates42@gmail.com>
 """

class RangeFilter():

	def __init__(self, field, min_value=None, max_value=None):

		self.field = field
		self.min = min_value
		self.max = max_value

		self.check_value = lambda s,x: False

		if not self.min is None and not self.max is None:
			self.check_value = self.fullrange

		elif not self.min is None and self.max is None:
			self.check_value = self.lowerbound

		elif self.min is None and not self.max is None:
			self.check_value = self.upperbound


	def fullrange(self, value):
		return (value >= self.min) and (value <= self.max)

	def lowerbound(self, value):
		return (value >= self.min)

	def upperbound(self, value):
		return (value <= self.max)

class SetFilter():

	def __init__(self, field, value_set=None):

		self.field = field
		self.value_set = set(value_set)

	def check_value(self, value):
		return value in self.value_set

class YearFilter(RangeFilter):

	def __init__(self, min_year=None, max_year=None):

		self.field = 'Year'
		self.min = min_year
		self.max = max_year

		self.check_value = lambda s,x: False

		if not self.min is None and not self.max is None:
			self.check_value = self.fullrange

		elif not self.min is None and self.max is None:
			self.check_value = self.lowerbound

		elif self.min is None and not self.max is None:
			self.check_value = self.upperbound
