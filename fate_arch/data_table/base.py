#
#  Copyright 2019 The FATE Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#


import abc
import pickle
from typing import Iterable

import six

from arch.api.utils.core_utils import current_timestamp, serialize_b64, deserialize_b64
from fate_flow.db.db_models import DB, MachineLearningDataSchema
from fate_flow.settings import stat_logger


@six.add_metaclass(abc.ABCMeta)
class Table(object):
    """
    table for distributed storage
    """

    @abc.abstractmethod
    def get_partitions(self):
        pass

    @abc.abstractmethod
    def get_storage_engine(self):
        pass

    @abc.abstractmethod
    def get_address(self):
        pass

    @abc.abstractmethod
    def get_namespace(self):
        pass

    @abc.abstractmethod
    def get_name(self):
        pass

    @abc.abstractmethod
    def put_all(self, kv_list: Iterable, use_serialize=True, chunk_size=100000):
        """
        Puts (key, value) 2-tuple stream from the iterable items.

        Elements must be exact 2-tuples, they may not be of any other type, or tuple subclass.
        Parameters
        ----------
        kv_list : Iterable
          Key-Value 2-tuple iterable. Will be serialized.
        Notes
        -----
        Each key must be less than 512 bytes, value must be less than 32 MB(implementation depends).
        """
        pass

    @abc.abstractmethod
    def collect(self, min_chunk_size=0, use_serialize=True) -> list:
        """
        Returns an iterator of (key, value) 2-tuple from the Table.

        Parameters
        ---------
        min_chunk_size : int
          Minimum chunk size (key bytes + value bytes) returned if end of table is not hit.
          0 indicates a default chunk size (partition_num * 1.75 MB)
          negative number indicates no chunk limit, i.e. returning all records.
          Default chunk size is recommended if there is no special needs from user.

        Returns
        -------
        Iterator
        """
        pass

    @abc.abstractmethod
    def count(self):
        """
        Returns the number of elements in the Table.

        Returns
        -------
        int
          Number of elements in this Table.
        """
        pass

    @abc.abstractmethod
    def save_as(self, name, namespace, partition=None, **kwargs):
        """
        Transforms a temporary table to a persistent table.

        Parameters
        ----------
        name : string
          Table name of result Table.
        namespace: string
          Table namespace of result Table.
        partition : int
          Number of partition for the new persistent table.
        use_serialize

        Returns
        -------
        Table
           Result persistent Table.
        """
        pass

    @abc.abstractmethod
    def close(self):
        pass

    def destroy(self):
        # destroy schema
        self.destroy_schema()
        # subclass method needs do: super().destroy()

    """
    meta utils
    """

    def get_schema(self, _type='schema'):
        with DB.connection_context():
            schema = MachineLearningDataSchema.select().where(MachineLearningDataSchema.f_table_name == self._name,
                                                              MachineLearningDataSchema.f_namespace == self._namespace)
            schema_data = {}
            if schema:
                schema = schema[0]
                try:
                    if _type == 'schema':
                        schema_data = deserialize_b64(schema.f_schema)
                    elif _type == 'data':
                        schema_data = deserialize_b64(schema.f_part_of_data)
                    elif _type == 'count':
                        schema_data = schema.f_count
                except:
                    schema_data = None
        return schema_data

    def save_schema(self, schema_data=None, party_of_data=None, count=0):
        # save metas to mysql
        if not schema_data:
            schema_data = {}
        if not party_of_data:
            party_of_data = []
        with DB.connection_context():
            schema = MachineLearningDataSchema.select().where(MachineLearningDataSchema.f_table_name == self._name,
                                                              MachineLearningDataSchema.f_namespace == self._namespace)
            if schema:
                # save schema info
                schema = schema[0]
                if schema.f_schema:
                    _schema_data = deserialize_b64(schema.f_schema)
                _schema_data.updata(schema_data)
                schema.f_schema = serialize_b64(_schema_data)
                # save data
                if party_of_data:
                    _f_part_of_data = deserialize_b64(schema.f_part_of_data)
                    if len(_f_part_of_data) < 200:
                        _f_part_of_data.append(party_of_data[:(200 - len(_f_part_of_data))])
                        schema.f_part_of_data = serialize_b64(party_of_data[:200])
                # save count
                if count:
                    schema.f_count += count
            else:
                raise Exception('please create table {} {} before useing'.format(self._namespace, self._namespace))
            schema.f_update_time = current_timestamp()
            schema.save(_insert=True)

    def destroy_schema(self):
        try:
            with DB.connection_context():
                MachineLearningDataSchema.delete().where(MachineLearningDataSchema.f_table_name == self._name,
                                                         MachineLearningDataSchema.f_namespace == self._namespace).execute()
        except Exception as e:
            stat_logger.error("delete_table_meta {}, {}, exception:{}.".format(self._namespace, self._name, e))


class StorageABC(metaclass=abc.ABCMeta):
    ...


class HDFSStorage(StorageABC):
    def __init__(self, path):
        self.path = path


class EggRollStorage(StorageABC):
    def __init__(self, name, namespace):
        self._name = name
        self._namespace = namespace


class MysqlAddress(StorageABC):
    def __init__(self, user, passwd, host, port, db, name):
        self.user = user
        self.passwd = passwd
        self.host = host
        self.port = port
        self.db = db
        self.name = name


