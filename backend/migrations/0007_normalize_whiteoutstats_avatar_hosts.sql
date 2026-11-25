-- WhiteoutStats historically supplied a misspelled Akamai avatar hostname.
-- The only persisted avatar URL field is player_whiteoutstats_profiles.avatar_url.
UPDATE player_whiteoutstats_profiles
SET avatar_url = 'https://gof-formal-avatar.akamaized.net' ||
  substr(avatar_url, length('https://gof-format-avatar.akamaized.net') + 1)
WHERE substr(avatar_url, 1, length('https://gof-format-avatar.akamaized.net')) =
      'https://gof-format-avatar.akamaized.net'
  AND (
    length(avatar_url) = length('https://gof-format-avatar.akamaized.net')
    OR substr(avatar_url, length('https://gof-format-avatar.akamaized.net') + 1, 1) IN ('/', '?', '#', ':')
  );
