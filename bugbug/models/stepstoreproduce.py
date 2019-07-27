# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import Pipeline

from bugbug import bug_features, bugzilla, feature_cleanup
from bugbug.model import BugModel
from bugbug.pulearning import PUClassifier


class StepsToReproduceModel(BugModel):
    def __init__(self, lemmatization=False):
        BugModel.__init__(self, lemmatization)

        self.calculate_importance = False
        self.pu_learning = True

        feature_extractors = [
            bug_features.has_regression_range(),
            bug_features.severity(),
            bug_features.keywords({"stepswanted"}),
            bug_features.is_coverity_issue(),
            bug_features.has_crash_signature(),
            bug_features.has_url(),
            bug_features.has_w3c_url(),
            bug_features.has_github_url(),
            bug_features.whiteboard(),
            bug_features.patches(),
            bug_features.landings(),
        ]

        cleanup_functions = [
            feature_cleanup.fileref(),
            feature_cleanup.url(),
            feature_cleanup.synonyms(),
        ]

        self.extraction_pipeline = Pipeline(
            [
                (
                    "bug_extractor",
                    bug_features.BugExtractor(feature_extractors, cleanup_functions),
                ),
                (
                    "union",
                    ColumnTransformer(
                        [
                            ("data", DictVectorizer(), "data"),
                            ("title", self.text_vectorizer(), "title"),
                            ("comments", self.text_vectorizer(), "comments"),
                        ]
                    ),
                ),
            ]
        )

        self.clf = PUClassifier(n_jobs=-1)

    def get_labels(self):
        classes = {}

        for bug_data in bugzilla.get_bugs():
            classes[int(bug_data["id"])] = 0
            for entry in bug_data["history"]:
                for change in entry["changes"]:
                    if change["removed"].startswith("stepswanted"):
                        classes[int(bug_data["id"])] = 1
            if "cf_has_str" in bug_data:
                if bug_data["cf_has_str"] == "yes":
                    classes[int(bug_data["id"])] = 1

        print(
            "{} bugs have no labels".format(
                sum(1 for label in classes.values() if label == 0)
            )
        )
        print(
            "{} bugs have steps to reproduce".format(
                sum(1 for label in classes.values() if label == 1)
            )
        )

        return classes, [0, 1]

    def overwrite_classes(self, bugs, classes, probabilities):
        for i, bug in enumerate(bugs):
            if "cf_has_str" in bug and bug["cf_has_str"] == "no":
                classes[i] = 0 if not probabilities else [1.0, 0.0]
            elif "cf_has_str" in bug and bug["cf_has_str"] == "yes":
                classes[i] = 1 if not probabilities else [0.0, 1.0]
            elif "stepswanted" in bug["keywords"]:
                classes[i] = 0 if not probabilities else [1.0, 0.0]

        return classes

    def get_feature_names(self):
        return self.extraction_pipeline.named_steps["union"].get_feature_names()
