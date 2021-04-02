# fil-rouge-kubernetes

# Architecture :
![architecture](https://user-images.githubusercontent.com/28030944/113333877-4672d000-9323-11eb-922c-1d4aa1e27b75.png)

# Decriptif du projet:

le projet consiste en la mise en place d'une API qui permet à un utilisateur d'uploader un fichier et de recevoir en retour en JSON contenant les données et les métadonnées du fichier. L'api accepte les images (png,jpeg,jpg,gif),txt,csv,mp4,pdf et docx. Pour les autres types de fichiers un message est retourné à l'utilisateur pour l'informer que le type du fichier n'est pas pris en compte.

# Utilisation de l'API:

L'API possède un seul End point qui est /upload.

L'API est accessible avec un curl :
curl -F "file=@/path/to/nom_fichier.extension" "https://filrouge.isbou.p2021.ajoga.fr/upload"

filrouge.isbou.p2021.ajoga.fr nom domaine associé à l'@IP de l'instance EC2.

Des fichiers de tests sont disponibles dans le dossier test.

# Descriptif - Partie Conteneurisation :

- le fichier Dockerfile qui permet d'empaqueter l'application se trouve au niveau du dossier fil_rouge
- docker-compose.yml : composé de deux services de l'api (j'ai préféré procéder ainsi au lieu de définir un seul service et faire un `docker compose scale` par la suite, pour avoir les deux instances de l'api toujours disponibles). D'un service nginx qui joue le role de load balancer et d'un service certbot qui automatise la partie SSL/TLS.
- Le dossier kubernetes contient tous les fichiers nécessaires pour déployer l'application dans un environnement kubernetes.

# Déploiement du cluster Kubernetes :

J'ai déployé un cluster kubernetes dans une instance EC2 de type t2.micro (1 CPU) grâce à la solution `K3D` qui permet de faire tourner `K3S` dans Docker. C'est la seule solution qui a fonctionnée avec la contrainte qu'on a avec le type d'instance EC2 (t2.micro). Mais une fois que je défini une resource Deployment de kubernetes, l'instance EC2 cesse de fonctionner. Toute fois j'ai mis le `kubeconfig` dans le dossier kubernetes.

Pour faire les tests en local, j'ai déployé un cluster kubernetes en utilisant la solution `kind`.

# Descriptif des fichiers contenus dans le dossier kubernetes

- app-deployment.yml : Resource Deployment qui permet de déployer 3 réplicas de l'api

Pour définir les credentials AWS dans les 3 pods, j'ai fait un montage de volume ( Ce n'est pas la meilleure manière de procéder, j'ai pensé à créer une ressource Secret et à définir les crendetials qui seront injéctées dans les pods lors de déploiement, mais on a une structure du fichier credentials qui est spéciale, deux profiles sont définies dans le fichier crédentials, un profile enseignant et un autre étudiant et le profile étudiant dépend de celui de l'enseignant)

Dans un premier temps j'ai crée le fichier credentials dans /root/.aws/credentials dans le noeud(conteneur) `kind-control-plane` du cluster kubernetes:
<img width="633" alt="Capture d’écran 2021-04-01 à 21 13 45" src="https://user-images.githubusercontent.com/28030944/113342859-4d9fdb00-932f-11eb-99c7-47f0d5da7567.png">

Déploiement des 3 pods :

<img width="633" alt="Capture d’écran 2021-04-01 à 21 19 44" src="https://user-images.githubusercontent.com/28030944/113343357-01a16600-9330-11eb-8e0a-69b8a09b1650.png">

- app-service.yml : Resource Service pour accéder à l'api
<img width="617" alt="Capture d’écran 2021-04-01 à 21 22 30" src="https://user-images.githubusercontent.com/28030944/113343652-68268400-9330-11eb-98f3-89212a1125f6.png">

- nginx-ingress.yml : NGINX Ingress Controller qui permet l'accès à l'api depuis internet avec un nom de domaine

<img width="118" alt="Capture d’écran 2021-04-01 à 21 27 28" src="https://user-images.githubusercontent.com/28030944/113344254-1f22ff80-9331-11eb-94b1-a3a9ef58eeed.png">

Installation de l'Ingress NGINX : `kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/master/deploy/static/provider/kind/deploy.yaml`

<img width="760" alt="Capture d’écran 2021-04-02 à 03 27 39" src="https://user-images.githubusercontent.com/28030944/113370172-7a6de580-9363-11eb-9b74-3cd453feb2ef.png">

<img width="933" alt="Capture d’écran 2021-04-01 à 21 32 32" src="https://user-images.githubusercontent.com/28030944/113344794-d750a800-9331-11eb-991a-8f74f6c4db4a.png">

*ADDRESS* localhost sera remplacé par l'@IP de mon instance EC2 en cas de déploiement dans AWS.

- app-hpa.yml : Resource HorizontalPodAutoscaler pour faire un autoscaling horizontal et passer de 3 à 6 pods quand le CPU au niveau du noeud atteint 80%.
Dans un premier temps j'ai installer l'api metrics qui n'existe pas par défaut (metrics-server.yml est le fichier yaml utilisé pour cela)
<img width="739" alt="Capture d’écran 2021-04-01 à 21 44 38" src="https://user-images.githubusercontent.com/28030944/113345957-7e820f00-9333-11eb-8f50-548b3c7f30b1.png">

