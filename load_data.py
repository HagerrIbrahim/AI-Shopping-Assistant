
import json
import psycopg

DB_NAME = "ai_shopping_assistant"
DB_USER = "postgres"
DB_PASSWORD = "Hager,808"
DB_HOST = "localhost"
DB_PORT = "5432"

DATASET_PATH = (
    r"C:\Users\DELL\OneDrive\Belgeler\GitHub"
    r"\AI-Shopping-Assistant\data\raw\meta_Amazon_Fashion.jsonl"
)


def clean_text(value):
    """Convert a value to text, or None if it is empty."""
    if isinstance(value, str):
        return value.strip() or None

    return None


def load_products():
    connection = psycopg.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )

    loaded = 0
    skipped = 0

    try:
        with connection.cursor() as cursor:
            with open(DATASET_PATH, "r", encoding="utf-8") as file:
                for line in file:
                    try:
                        product = json.loads(line)

                        title = clean_text(product.get("title"))
                        if not title:
                            skipped += 1
                            continue

                        description = product.get("description")
                        if isinstance(description, list):
                            description = "\n".join(
                                str(item) for item in description
                                if item
                            )
                        elif not isinstance(description, str):
                            description = None

                        rating = product.get("average_rating")
                        rating_count = product.get("rating_number")
                        price = product.get("price")

                        # Insert the main product
                        cursor.execute(
                            """
                            INSERT INTO products (
                                source_product_id,
                                source,
                                title,
                                domain,
                                price,
                                currency,
                                average_rating,
                                rating_count,
                                description,
                                brand
                            )
                            VALUES (
                                %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s
                            )
                            RETURNING product_id
                            """,
                            (
                                clean_text(product.get("parent_asin")),
                                "Amazon",
                                title,
                                clean_text(product.get("main_category"))
                                or "AMAZON FASHION",
                                price,
                                None,
                                rating,
                                rating_count,
                                description,
                                clean_text(product.get("store"))
                            )
                        )

                        product_id = cursor.fetchone()[0]

                        # Insert images
                        images = product.get("images") or []

                        for image_data in images:
                            if not isinstance(image_data, dict):
                                continue

                            image_url = (
                                clean_text(image_data.get("hi_res"))
                                or clean_text(image_data.get("large"))
                                or clean_text(image_data.get("thumb"))
                            )

                            if not image_url:
                                continue

                            variant = clean_text(
                                image_data.get("variant")
                            )
                            is_primary = variant == "MAIN"

                            cursor.execute(
                                """
                                INSERT INTO productimages (
                                    product_id,
                                    image_url,
                                    variant,
                                    is_primary
                                )
                                VALUES (%s, %s, %s, %s)
                                """,
                                (
                                    product_id,
                                    image_url,
                                    variant,
                                    is_primary
                                )
                            )

                        # Insert features
                        features = product.get("features") or []

                        for index, feature in enumerate(features, start=1):
                            feature_text = clean_text(feature)

                            if not feature_text:
                                continue

                            cursor.execute(
                                """
                                INSERT INTO product_features (
                                    product_id,
                                    feature_text,
                                    feature_order
                                )
                                VALUES (%s, %s, %s)
                                """,
                                (product_id, feature_text, index)
                            )

                        # Insert videos
                        videos = product.get("videos") or []

                        for video in videos:
                            if not isinstance(video, dict):
                                continue

                            cursor.execute(
                                """
                                INSERT INTO product_videos (
                                    product_id,
                                    video_title,
                                    video_url,
                                    user_id
                                )
                                VALUES (%s, %s, %s, %s)
                                """,
                                (
                                    product_id,
                                    clean_text(video.get("title")),
                                    clean_text(video.get("url")),
                                    clean_text(video.get("user_id"))
                                )
                            )

                        loaded += 1

                        # Commit every 500 products
                        if loaded % 500 == 0:
                            connection.commit()
                            print(f"Loaded {loaded} products...")

                    except (json.JSONDecodeError, TypeError, ValueError) as error:
                        skipped += 1
                        print("Skipped invalid record:", error)

                    except psycopg.Error:
                        connection.rollback()
                        raise

            connection.commit()

        print("\nLoading finished!")
        print("Products loaded:", loaded)
        print("Records skipped:", skipped)

    finally:
        connection.close()


if __name__ == "__main__":
    load_products()
