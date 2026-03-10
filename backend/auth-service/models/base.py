from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    __abstract__ = True
    
    def to_json(self):
        return {k: v for k, v in self.__dict__.items() if k != '_sa_instance_state'}
