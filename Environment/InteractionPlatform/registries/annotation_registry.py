from components.annotation import Annotation


class AnnotationRegistry:

    def __init__(self):
        self.annotations = {}

    def add_annotation(self, a: Annotation):
        print("add annotation in annotation registry")
        self.annotations[a.url] = a
        print("annotation keys: ", self.annotations.keys())

    def add_annotation_list(self, annotation_list: list):
        for a in annotation_list:
            self.annotations[a.url] = a

    def get_annotations(self):
        return self.annotations

    def get_annotation_list(self):
        return list(self.annotations.values())

    def __iter__(self):
        return iter(self.annotations)

    def get_by_id(self, identifier):
        a = None
        if identifier in self.annotations.keys():
            a = self.annotations[identifier]
        else:
            print("annotation does not have correct id")
        return a
