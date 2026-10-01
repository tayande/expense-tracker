"""Tests for profile photo upload, removal and viewing.

TestConfig sets ADMIN_EMAILS = {"admin@example.com"}.
"""
import io

import pytest
from PIL import Image

from models import db, ProfilePhoto


def make_image(fmt="PNG", size=(400, 300), mode="RGB", color=(200, 30, 30)):
    """Create an image file in memory, like a user's photo."""
    buffer = io.BytesIO()
    if mode == "RGBA":
        color = (*color, 0)          # fully transparent
    Image.new(mode, size, color).save(buffer, format=fmt)
    buffer.seek(0)
    return buffer


def upload(client, file_obj, filename="me.png"):
    return client.post(
        "/settings/photo",
        data={"photo": (file_obj, filename)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def stored_image():
    """Open the photo saved in the database for the only user that has one."""
    photo = ProfilePhoto.query.one()
    return Image.open(io.BytesIO(photo.data))


# --- Uploading -------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP", "GIF"])
def test_supported_formats_are_accepted(logged_in_client, fmt):
    response = upload(logged_in_client, make_image(fmt), f"me.{fmt.lower()}")

    assert b"Profile photo updated" in response.data
    assert stored_image().format == "JPEG"     # everything is stored as JPEG


def test_photo_is_cropped_to_256_square(logged_in_client):
    upload(logged_in_client, make_image(size=(1200, 500)))   # very wide photo

    assert stored_image().size == (256, 256)


def test_transparent_png_gets_white_background(logged_in_client):
    upload(logged_in_client, make_image(mode="RGBA"))

    red, green, blue = stored_image().getpixel((128, 128))
    assert min(red, green, blue) > 240         # white-ish, not black


def test_uploading_again_replaces_the_old_photo(logged_in_client):
    upload(logged_in_client, make_image(color=(255, 0, 0)))
    upload(logged_in_client, make_image(color=(0, 0, 255)))

    assert ProfilePhoto.query.count() == 1
    red, _, blue = stored_image().getpixel((128, 128))
    assert blue > red                          # the new blue photo won


def test_fake_image_is_rejected(logged_in_client):
    fake = io.BytesIO(b"<script>alert('not a photo')</script>")

    response = upload(logged_in_client, fake, "photo.jpg")   # lies about being a JPG

    assert b"isn&#39;t an image we can read" in response.data
    assert ProfilePhoto.query.count() == 0


def test_unsupported_image_format_is_rejected(logged_in_client):
    response = upload(logged_in_client, make_image("BMP"), "me.bmp")

    assert b"Please upload a JPG, PNG, WebP or GIF" in response.data
    assert ProfilePhoto.query.count() == 0


def test_no_file_chosen_is_rejected(logged_in_client):
    response = logged_in_client.post("/settings/photo", data={},
                                     content_type="multipart/form-data",
                                     follow_redirects=True)

    assert b"Please choose a photo" in response.data


def test_file_over_5mb_is_rejected_politely(logged_in_client):
    huge = io.BytesIO(b"0" * (5 * 1024 * 1024 + 1))

    response = upload(logged_in_client, huge, "huge.jpg")

    assert b"under 5 MB" in response.data      # friendly message, not a crash page
    assert ProfilePhoto.query.count() == 0


def test_decompression_bomb_is_rejected(logged_in_client):
    # A small file that claims to be 6000x6000 = 36 million pixels
    bomb = make_image(size=(6000, 6000), color=(0, 0, 0))
    assert len(bomb.getvalue()) < 5 * 1024 * 1024   # passes the size check...

    response = upload(logged_in_client, bomb)

    assert b"too large" in response.data            # ...but is still refused
    assert ProfilePhoto.query.count() == 0


def test_upload_requires_login(client):
    response = client.post("/settings/photo", data={"photo": (make_image(), "me.png")},
                           content_type="multipart/form-data")

    assert "/login" in response.headers["Location"]
    assert ProfilePhoto.query.count() == 0


# --- Removing -------------------------------------------------------------------

def test_remove_photo(logged_in_client):
    upload(logged_in_client, make_image())

    response = logged_in_client.post("/settings/photo/delete", follow_redirects=True)

    assert b"Profile photo removed" in response.data
    assert ProfilePhoto.query.count() == 0


# --- Viewing -----------------------------------------------------------------------

def avatar_url_for(client, user_id):
    """The /avatar/... URL as it appears on the settings page."""
    html = client.get("/settings").get_data(as_text=True)
    start = html.index(f"/avatar/{user_id}")
    return html[start:html.index('"', start)]


def test_owner_can_view_own_photo(logged_in_client):
    upload(logged_in_client, make_image())

    response = logged_in_client.get(avatar_url_for(logged_in_client, 1))

    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_other_users_cannot_view_your_photo(app, logged_in_client, make_user):
    upload(logged_in_client, make_image())          # alice (id 1) uploads

    make_user(username="mallory", email="mallory@example.com")
    other = app.test_client()
    other.post("/login", data={"username": "mallory", "password": "password123"})

    assert other.get("/avatar/1").status_code == 404


def test_admin_can_view_anyones_photo(app, logged_in_client, make_user):
    upload(logged_in_client, make_image())          # alice (id 1) uploads

    make_user(username="boss", email="admin@example.com")
    admin = app.test_client()
    admin.post("/login", data={"username": "boss", "password": "password123"})

    assert admin.get("/avatar/1").status_code == 200


def test_photo_requires_login(client):
    assert "/login" in client.get("/avatar/1").headers["Location"]


def test_missing_photo_is_404(logged_in_client):
    assert logged_in_client.get("/avatar/1").status_code == 404


def test_photo_url_changes_when_photo_changes(logged_in_client):
    upload(logged_in_client, make_image())
    first_url = avatar_url_for(logged_in_client, 1)

    photo = ProfilePhoto.query.one()
    photo.updated_at = photo.updated_at.replace(year=photo.updated_at.year - 1)
    db.session.commit()

    assert avatar_url_for(logged_in_client, 1) != first_url   # browsers won't show a stale photo


# --- Display -----------------------------------------------------------------------

def test_top_bar_shows_initial_without_photo(logged_in_client):
    html = logged_in_client.get("/dashboard").get_data(as_text=True)

    assert 'class="avatar avatar-sm avatar-initial"' in html
    assert ">A</span>" in html                        # "A" for alice


def test_top_bar_shows_photo_after_upload(logged_in_client):
    upload(logged_in_client, make_image())

    html = logged_in_client.get("/dashboard").get_data(as_text=True)

    assert '<img src="/avatar/1?v=' in html


def test_admin_inbox_shows_sender_photo(app, logged_in_client, make_user):
    upload(logged_in_client, make_image())
    logged_in_client.post("/feedback", data={"message": "Nice app"})

    make_user(username="boss", email="admin@example.com")
    admin = app.test_client()
    admin.post("/login", data={"username": "boss", "password": "password123"})

    html = admin.get("/admin").get_data(as_text=True)

    assert '<img src="/avatar/1?v=' in html