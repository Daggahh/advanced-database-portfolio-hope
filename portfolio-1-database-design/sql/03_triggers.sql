-- FitsCheck triggers: rules that must read another table, which a CHECK cannot do,
-- plus server-side updated_at stamping. Violations raise SQLSTATE 23514 (check_violation)
-- so clients handle them exactly like a CHECK constraint failure.

SET search_path = fitscheck;

CREATE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_app_user_updated_at BEFORE UPDATE ON app_user
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_post_updated_at BEFORE UPDATE ON post
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_comment_updated_at BEFORE UPDATE ON comment
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- BR-03: a blocked user cannot follow the person who blocked them
CREATE FUNCTION follow_not_blocked() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM block
               WHERE blocker_id = NEW.followed_id AND blocked_id = NEW.follower_id) THEN
        RAISE EXCEPTION 'user % is blocked by user % and cannot follow them',
                        NEW.follower_id, NEW.followed_id
            USING ERRCODE = 'check_violation', CONSTRAINT = 'tg_follow_not_blocked';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_follow_not_blocked BEFORE INSERT OR UPDATE ON follow
    FOR EACH ROW EXECUTE FUNCTION follow_not_blocked();

-- BR-03 again from the other side: blocking removes an existing follow, otherwise the rule
-- would only stop new follows and leave the old one in place
CREATE FUNCTION block_removes_follow() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM follow WHERE follower_id = NEW.blocked_id AND followed_id = NEW.blocker_id;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_block_removes_follow AFTER INSERT ON block
    FOR EACH ROW EXECUTE FUNCTION block_removes_follow();

-- BR-12: a user cannot vote on their own post
CREATE FUNCTION vote_not_own_post() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM post WHERE id = NEW.post_id AND author_id = NEW.user_id) THEN
        RAISE EXCEPTION 'user % cannot vote on their own post %', NEW.user_id, NEW.post_id
            USING ERRCODE = 'check_violation', CONSTRAINT = 'tg_vote_not_own_post';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_vote_not_own_post BEFORE INSERT OR UPDATE ON vote
    FOR EACH ROW EXECUTE FUNCTION vote_not_own_post();
