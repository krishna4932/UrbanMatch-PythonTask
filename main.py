import json
import re

from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import case, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
import models, schemas

app = FastAPI()

Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


#Create a user and returns created data
@app.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = models.User(**user.dict())
    validate_user_input(db_user)
    parse_interests(db_user)

    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
    except IntegrityError:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )
    except Exception:
        raise HTTPException(status_code=500, detail=str('Internal Error. Try again'))

    return parse_to_response(db_user)


# @app.post("/users/list", response_model=list[schemas.User])
# def bulk_upload_users(users: list[schemas.UserCreate], db: Session = Depends(get_db)):
#     st = []
#     for user in users:
#         db_user = models.User(**user.dict())
#         parse_interests(db_user)
#         st.append(db_user)
#     db.bulk_save_objects(st)
#     db.commit()
#     return [parse_to_response(i) for i in st]


#get all users
@app.get("/users/", response_model=list[schemas.User])
def read_users(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    users = db.query(models.User).offset(skip).limit(limit).all()
    return [parse_to_response(user) for user in users]


#get a single user
@app.get("/users/{user_id}", response_model=schemas.User)
def read_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return parse_to_response(user)

#update a used based on id
@app.put("/users/{user_id}", response_model=schemas.User)
def update_user(user: schemas.UserUpdate, user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    validate_user_input(user)

    updated_user = user.dict(exclude_unset=True)
    for field, value in updated_user.items():
        setattr(db_user, field, value)

    if user.interests is not None:
        parse_interests(db_user)

    try:
        db.commit()
        db.refresh(db_user)
    except IntegrityError:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )
    except Exception:
        raise HTTPException(status_code=500, detail=str('Internal Error. Try again'))

    return parse_to_response(db_user)


# deletes user
@app.delete("/users/{user_id}", response_model=schemas.User)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(db_user)
    db.commit()
    return parse_to_response(db_user)


"""
Find matches - V1 - The SQL queries are executed directly within the database
Load handled by the database itself

Assumptions on match making:

Preference given more to the opposite gender, no.of interests that are common and Age difference.
Also if they are in same city its a plus.
Age limit scores more on opposite genders, also handles male, female gender cases while scoring age(if mentioned or defaults).
"""
@app.get("/v1/matches/user/{user_id}/", response_model=list[schemas.User])
def find_matches(user_id: int, skip: int = 0, limit: int = 10, age_limit: int = 5, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    gender_score = case(
        [(models.User.gender.isnot(db_user.gender), 500)],
        else_=0
    )

    city_score = case(
        [(models.User.city.is_(db_user.city), 10)],
        else_=0
    )

    total_score = gender_score + city_score
    for item in json.loads(db_user.interests):
        total_score += case(
            [(models.User.interests.contains(f'%{item}%'), 10)],
            else_=0
        )

    total_score += case(
        [
            (and_(
                models.User.gender != db_user.gender,
                models.User.age.between(db_user.age - age_limit, db_user.age + age_limit)
            ), 10)
        ],
        else_=0
    )

    if (db_user.gender == "M"):
        total_score += case(
            [(models.User.age.between(db_user.age - age_limit, db_user.age), 50)],
            else_=0
        )
    elif (db_user.gender == "F"):
        total_score += case(
            [(models.User.age.between(db_user.age, db_user.age + age_limit), 50)],
            else_=0
        )

    matched_users = (
        db.query(models.User)
        .filter(models.User.id != user_id)
        .order_by(total_score.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [parse_to_response(user) for user in matched_users]


"""
Find matches - V2 - Data is retrieved from the database first, 
and then filtering and scoring are performed in the application layer using Python.

Load handled by the application.

Assumptions on match making(same as V1):

Preference given more to the opposite gender, no.of interests that are common and Age difference(if mentioned or defaults).
Also if they are in same city its a plus.
Age limit scores more on opposite genders, also handles male, female gender cases while scoring age.
"""
@app.get("/v2/matches/user/{user_id}/", response_model=list[schemas.User])
def find_matches(user_id: int, skip: int = 0, limit: int = 10, age_limit: int = 5, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    parse_to_response(db_user)

    users = (
        db.query(models.User)
        .filter(models.User.id != user_id)
        .all()
    )

    [parse_to_response(user) for user in users]

    def calculate_score(user):
        score = 0
        if user.gender != db_user.gender:
            score += 500
            if db_user.age - age_limit <= user.age <= db_user.age + age_limit:
                score += 10
        if user.city == db_user.city:
            score += 10
        if db_user.gender == 'M' and db_user.age - age_limit <= user.age <= db_user.age:
            score += 50
        elif db_user.gender == 'F' and db_user.age <= user.age <= db_user.age + age_limit:
            score += 50

        score += len(list(set(user.interests) & set(db_user.interests))) * 10
        return score

    # Sort based on score
    users.sort(key=calculate_score, reverse=True)

    return users[skip:skip + limit]


#-----------------------UTILS--------------------#


def parse_interests(db_user):
    db_user.interests = json.dumps(db_user.interests)


def parse_to_response(db_user):
    db_user.interests = json.loads(db_user.interests)
    return db_user


"""
Handling email and age validation
"""
def validate_user_input(user):
    if user.email is not None and not validate_email(user.email):
        raise HTTPException(status_code=400, detail="Email must be valid")
    if user.age is not None and user.age < 18:
        raise HTTPException(status_code=400, detail="Minors can't be registered: age should be 18+")


def validate_email(email):
    return re.match(r'[^@]+@[^@]+\.[^@]+', email)
