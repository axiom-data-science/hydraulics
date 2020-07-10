CREATE TABLE ifcb_sample_stats
(
    time                INT        NOT NULL,
    ifcb_id             VARCHAR(7) NOT NULL,
    roi                 INT        NOT NULL,
    name                VARCHAR    NOT NULL,
    prob                FLOAT      NOT NULL,
    classifier          VARCHAR    NOT NULL,
    classification_time INT        NOT NULL,
    biovolume           FLOAT      NOT NULL,
    carbon              FLOAT      NOT NULL,
    hab                 BOOLEAN    NOT NULL,
    PRIMARY KEY (time, ifcb_id, roi)
);
COMMENT ON COLUMN ifcb_sample_stats.time IS 'observation in UTC';
COMMENT ON COLUMN ifcb_sample_stats.ifcb_id IS 'IFCB station name';
COMMENT ON COLUMN ifcb_sample_stats.roi IS 'roi from sample bin';
COMMENT ON COLUMN ifcb_sample_stats.name IS 'Name of samples';
COMMENT ON COLUMN ifcb_sample_stats.prob IS 'classification probability';
COMMENT ON COLUMN ifcb_sample_stats.classification_time IS 'timestamp of classification';
COMMENT ON COLUMN ifcb_sample_stats.biovolume IS 'biovolume of sample in pg/L';
COMMENT ON COLUMN ifcb_sample_stats.carbon IS 'carbon content of sample in ug/L';
COMMENT ON COLUMN ifcb_sample_stats.hab IS 'is a HAB species';

create INDEX on ifcb_sample_stats (ifcb_id, time);
create INDEX on ifcb_sample_stats (ifcb_id, time, hab);