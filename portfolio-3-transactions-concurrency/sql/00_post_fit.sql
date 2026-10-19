-- post_fit: posting a fit as one unit of work. A post, its images, its hashtags and the hashtag
-- counters either all exist or none do, because a function runs inside its caller's transaction and
-- any error rolls back everything it did. It also holds BR-07 ("1 to 10 images"), a rule that spans
-- several rows and so cannot be a CHECK constraint.

SET search_path = fitscheck;

CREATE FUNCTION post_fit(p_author bigint, p_caption text, p_images text[], p_tags text[] DEFAULT '{}')
RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE
    v_post   bigint;
    v_tag    text;
    v_tag_id bigint;
BEGIN
    IF coalesce(cardinality(p_images), 0) NOT BETWEEN 1 AND 10 THEN
        RAISE EXCEPTION 'a post needs 1 to 10 images, got %', coalesce(cardinality(p_images), 0)
            USING ERRCODE = 'check_violation', CONSTRAINT = 'tx_post_has_images';
    END IF;

    INSERT INTO post (author_id, caption) VALUES (p_author, p_caption) RETURNING id INTO v_post;

    INSERT INTO post_image (post_id, position, image_url)
    SELECT v_post, ord, url FROM unnest(p_images) WITH ORDINALITY AS t(url, ord);

    FOREACH v_tag IN ARRAY ARRAY(SELECT DISTINCT unnest(p_tags)) LOOP
        -- The upsert increments the counter in the same statement that finds or creates the tag, so
        -- two posts using the same new tag at once cannot lose an increment (BR-20)
        INSERT INTO hashtag (name, posts_count) VALUES (v_tag, 1)
        ON CONFLICT (name) DO UPDATE SET posts_count = hashtag.posts_count + 1
        RETURNING id INTO v_tag_id;
        INSERT INTO post_hashtag (post_id, hashtag_id) VALUES (v_post, v_tag_id);
    END LOOP;

    RETURN v_post;
END;
$$;
